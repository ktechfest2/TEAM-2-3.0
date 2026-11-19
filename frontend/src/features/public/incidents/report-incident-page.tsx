import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2Icon,
  CopyIcon,
  FileClockIcon,
  ImageUpIcon,
  LocateFixedIcon,
  PhoneCallIcon,
  RotateCcwIcon,
  SearchIcon,
  ShieldCheckIcon,
  Trash2Icon,
  WifiOffIcon,
  XIcon,
} from 'lucide-react'
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { describedBy, FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '@/features/auth/auth-context'
import { useLgas, usePollingUnitSearch, useStates, useWards } from '@/features/directory/api'
import { LocationSelect } from '@/features/directory/location-select'
import { useElections } from '@/features/evidence/api'
import { ACCEPT_ATTRIBUTE, checkEvidenceFile, formatBytes, imageDimensions } from '@/features/evidence/file-checks'
import { useTrackIncident } from '@/features/incidents/api'
import { BandBadge } from '@/features/incidents/badges'
import { BAND_DESCRIPTIONS, INCIDENT_CATEGORIES, type IncidentCategory } from '@/features/incidents/types'
import {
  deleteIncidentDraft,
  draftKeys,
  isLegacyDraft,
  queueIncidentReport,
  syncIncidentReports,
  useDeleteIncidentDraft,
  useIncidentDrafts,
  useRetryIncidentDraft,
} from '@/features/public/incidents/drafts'
import { incidentReportSchema, type IncidentReportInput } from '@/features/public/incidents/schema'
import { useT } from '@/i18n/locale-provider'
import { ApiError } from '@/lib/api-client'
import { db } from '@/lib/offline/db'
import { useOnlineStatus } from '@/lib/offline/use-online-status'

const MAX_PHOTO_BYTES = 8 * 1024 * 1024
const MIN_PHOTO_SIDE = 200
const DESCRIPTION_HINT =
  'Say what happened, where and when, and what you saw yourself. Do not name private individuals or include phone numbers.'
const PRIVACY_POINTS = [
  'VoteTrace does not store your IP address, device identifiers or phone number with a report.',
  'Location and camera details are removed from photos before they are stored.',
  'Phone numbers and e-mail addresses typed into the description are masked.',
  'Photos are private. Only authorised reviewers can open them, and they are never published.',
  'Your network provider and our hosting provider can still see that a connection was made.',
]

const dateFormatter = new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium', timeStyle: 'short' })

type Photo = { data: ArrayBuffer; name: string; type: string; size: number; previewUrl: string }

type Outcome =
  | { kind: 'sent'; reference: string; receivedAt: string; photoStored: boolean }
  | { kind: 'queued'; offline: boolean }

function localNow() {
  const now = new Date()
  now.setSeconds(0, 0)
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

function IncidentReportForm({ onDone }: { onDone: (outcome: Outcome) => void }) {
  const t = useT()
  const queryClient = useQueryClient()
  const { user, isPreview } = useAuth()
  const signedIn = Boolean(user && !isPreview)
  const elections = useElections()
  const [photo, setPhoto] = useState<Photo | null>(null)
  const [photoError, setPhotoError] = useState<string>()
  const [geoMessage, setGeoMessage] = useState<string>()
  const [formError, setFormError] = useState<string>()
  const photoInput = useRef<HTMLInputElement>(null)

  const {
    register,
    handleSubmit,
    control,
    getValues,
    setValue,
    formState: { errors, isSubmitting, isSubmitted },
  } = useForm<IncidentReportInput>({
    resolver: zodResolver(incidentReportSchema),
    defaultValues: {
      electionId: '',
      category: undefined,
      stateId: '',
      lgaId: '',
      wardId: '',
      pollingUnitId: '',
      occurredAt: localNow(),
      timeIsApproximate: true,
      description: '',
      latitude: '',
      longitude: '',
      identity: 'anonymous',
    },
  })

  const [stateId, lgaId, wardId, pollingUnitId, latitude] = useWatch({
    control,
    name: ['stateId', 'lgaId', 'wardId', 'pollingUnitId', 'latitude'],
  })
  const states = useStates()
  const lgas = useLgas(stateId || undefined)
  const wards = useWards(lgaId || undefined)
  const units = usePollingUnitSearch({ wardId: wardId || undefined, pageSize: 100 }, Boolean(wardId))
  const electionList = elections.data?.data.items ?? []

  useEffect(() => () => (photo ? URL.revokeObjectURL(photo.previewUrl) : undefined), [photo])
  const onlyElectionId = electionList.length === 1 ? electionList[0]!.id : undefined
  useEffect(() => {
    if (onlyElectionId && !getValues('electionId')) setValue('electionId', onlyElectionId)
  }, [onlyElectionId, getValues, setValue])

  const setLocation = (next: { stateId?: string; lgaId?: string; wardId?: string }) => {
    const options = { shouldValidate: isSubmitted }
    setValue('stateId', next.stateId ?? '', options)
    setValue('lgaId', next.lgaId ?? '', options)
    setValue('wardId', next.wardId ?? '', options)
    setValue('pollingUnitId', '', options)
  }

  async function onPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setPhotoError(undefined)
    if (file.size > MAX_PHOTO_BYTES) return setPhotoError(t('The photo is larger than 8 MB.'))
    try {
      const data = await file.arrayBuffer()
      const check = checkEvidenceFile(file.name, file.size, new Uint8Array(data.slice(0, 16)))
      if (!check.ok) return setPhotoError(check.message)
      const size = await imageDimensions(file)
      if (size && Math.min(size.width, size.height) < MIN_PHOTO_SIDE) {
        return setPhotoError(t('The photo is too small. Use one at least 200 pixels on each side.'))
      }
      setPhoto({ data, name: file.name || 'photo.jpg', type: check.type, size: file.size, previewUrl: URL.createObjectURL(file) })
    } catch {
      setPhotoError(t('The photo could not be read. Try another one.'))
    }
  }

  function shareLocation() {
    if (!('geolocation' in navigator)) return setGeoMessage(t('This browser cannot share a location.'))
    setGeoMessage(t('Getting your location…'))
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setValue('latitude', position.coords.latitude.toFixed(4), { shouldValidate: true })
        setValue('longitude', position.coords.longitude.toFixed(4), { shouldValidate: true })
        setGeoMessage(t('Location added, rounded to about 10 metres.'))
      },
      () => setGeoMessage(t('Location was not shared. You can type it or leave it blank.')),
      { enableHighAccuracy: false, timeout: 15_000, maximumAge: 60_000 },
    )
  }

  function locationHint(values: IncidentReportInput) {
    const unit = units.data?.data.items.find((item) => item.id === values.pollingUnitId)
    if (unit) return `${unit.code} · ${unit.name}`
    const ward = wards.data?.data.items.find((item) => item.id === values.wardId)
    const lga = lgas.data?.data.items.find((item) => item.id === values.lgaId)
    const state = states.data?.data.items.find((item) => item.id === values.stateId)
    return [ward?.name, lga?.name, state?.name].filter(Boolean).join(', ')
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(undefined)
    let draftId: string
    try {
      const draft = await queueIncidentReport({
        electionId: values.electionId,
        category: values.category,
        description: values.description,
        locationHint: locationHint(values),
        stateId: values.stateId,
        lgaId: values.lgaId,
        wardId: values.wardId || undefined,
        pollingUnitId: values.pollingUnitId || undefined,
        occurredAt: values.occurredAt,
        timeIsApproximate: values.timeIsApproximate,
        latitude: values.latitude ? Number(values.latitude) : undefined,
        longitude: values.longitude ? Number(values.longitude) : undefined,
        protectIdentity: signedIn && values.identity === 'protected',
        asAccount: signedIn && values.identity !== 'anonymous',
        photo: photo ? { data: photo.data, name: photo.name, type: photo.type } : null,
      })
      draftId = draft.id
    } catch {
      setFormError(t('The report could not be saved on this device. Free some storage space and try again.'))
      return
    }

    if (!navigator.onLine) {
      void queryClient.invalidateQueries({ queryKey: draftKeys.all })
      onDone({ kind: 'queued', offline: true })
      return
    }
    await syncIncidentReports()
    let saved = await db.incidentDrafts.get(draftId)
    if (saved?.syncStatus === 'queued') {
      await syncIncidentReports()
      saved = await db.incidentDrafts.get(draftId)
    }
    void queryClient.invalidateQueries({ queryKey: draftKeys.all })
    if (saved?.syncStatus === 'synced' && saved.reference) {
      onDone({
        kind: 'sent',
        reference: saved.reference,
        receivedAt: saved.receivedAt ?? new Date().toISOString(),
        photoStored: Boolean(photo),
      })
      return
    }
    if (saved?.permanentFailure) {
      // The server refused the report as it stands; keep the form so it can be corrected.
      await deleteIncidentDraft(draftId)
      void queryClient.invalidateQueries({ queryKey: draftKeys.all })
      setFormError(saved.lastError ?? t('The report was not accepted. Check the details and try again.'))
      return
    }
    onDone({ kind: 'queued', offline: false })
  })

  const latitudeError = errors.latitude?.message
  const longitudeError = errors.longitude?.message

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('Incident details')}</CardTitle>
        <CardDescription>{t('Fields marked * are required. Everything else helps reviewers but is optional.')}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="space-y-6" aria-label={t('Incident report')}>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField id="incident-election" label={t('Election')} required error={errors.electionId?.message}>
              <Select
                id="incident-election"
                disabled={elections.isPending}
                aria-invalid={Boolean(errors.electionId)}
                aria-describedby={describedBy('incident-election', errors.electionId?.message)}
                {...register('electionId')}
              >
                <option value="">{elections.isPending ? t('Loading elections…') : t('Choose an election')}</option>
                {electionList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="incident-category" label={t('Category')} required error={errors.category?.message}>
              <Select
                id="incident-category"
                defaultValue=""
                aria-invalid={Boolean(errors.category)}
                aria-describedby={describedBy('incident-category', errors.category?.message)}
                {...register('category')}
              >
                <option value="" disabled>
                  {t('Select a category')}
                </option>
                {(Object.keys(INCIDENT_CATEGORIES) as IncidentCategory[]).map((key) => (
                  <option key={key} value={key}>
                    {t(INCIDENT_CATEGORIES[key])}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          {elections.isError && (
            <p role="alert" className="text-sm text-destructive">
              {t('Elections could not be loaded. Check your connection and try again.')}
            </p>
          )}

          <fieldset className="space-y-4">
            <legend className="mb-2 text-sm font-semibold">{t('Where did it happen?')}</legend>
            <LocationSelect
              idPrefix="incident-location"
              pick
              required={['state', 'lga']}
              errors={{ state: errors.stateId?.message, lga: errors.lgaId?.message }}
              value={{ stateId: stateId || undefined, lgaId: lgaId || undefined, wardId: wardId || undefined }}
              onChange={setLocation}
            />
            <FormField
              id="incident-polling-unit"
              label={t('Polling unit')}
              hint={wardId ? t('Optional. Leave blank if you are not sure.') : t('Choose a ward to list its polling units.')}
            >
              <Select
                id="incident-polling-unit"
                value={pollingUnitId}
                disabled={!wardId || units.isPending}
                aria-describedby="incident-polling-unit-hint"
                onChange={(event) => setValue('pollingUnitId', event.target.value)}
              >
                <option value="">{wardId ? t('Not sure or not at a polling unit') : t('Choose a ward first')}</option>
                {units.data?.data.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.code} · {item.name}
                  </option>
                ))}
              </Select>
            </FormField>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="mb-2 text-sm font-semibold">{t('When did it happen?')}</legend>
            <div className="grid items-end gap-4 sm:grid-cols-2">
              <FormField id="incident-time" label={t('Date and time')} required error={errors.occurredAt?.message}>
                <Input
                  id="incident-time"
                  type="datetime-local"
                  max={localNow()}
                  aria-invalid={Boolean(errors.occurredAt)}
                  aria-describedby={describedBy('incident-time', errors.occurredAt?.message)}
                  {...register('occurredAt')}
                />
              </FormField>
              <label className="flex items-center gap-2 pb-2 text-sm">
                <input type="checkbox" className="size-4 accent-primary" {...register('timeIsApproximate')} />
                {t('The time is approximate')}
              </label>
            </div>
          </fieldset>

          <FormField
            id="incident-description"
            label={t('What happened?')}
            required
            hint={t(DESCRIPTION_HINT)}
            error={errors.description?.message}
          >
            <Textarea
              id="incident-description"
              rows={6}
              maxLength={2000}
              aria-invalid={Boolean(errors.description)}
              aria-describedby={describedBy('incident-description', errors.description?.message, DESCRIPTION_HINT)}
              {...register('description')}
            />
          </FormField>

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">{t('Map location (optional)')}</legend>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={shareLocation}>
                <LocateFixedIcon />
                {t('Use my current location')}
              </Button>
              {latitude && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setValue('latitude', '')
                    setValue('longitude', '')
                    setGeoMessage(undefined)
                  }}
                >
                  <XIcon />
                  {t('Remove location')}
                </Button>
              )}
            </div>
            {geoMessage && (
              <p className="text-xs text-muted-foreground" aria-live="polite">
                {geoMessage}
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="incident-latitude" label={t('Latitude')} error={latitudeError}>
                <Input
                  id="incident-latitude"
                  inputMode="decimal"
                  aria-invalid={Boolean(latitudeError)}
                  aria-describedby={describedBy('incident-latitude', latitudeError)}
                  {...register('latitude')}
                />
              </FormField>
              <FormField id="incident-longitude" label={t('Longitude')} error={longitudeError}>
                <Input
                  id="incident-longitude"
                  inputMode="decimal"
                  aria-invalid={Boolean(longitudeError)}
                  aria-describedby={describedBy('incident-longitude', longitudeError)}
                  {...register('longitude')}
                />
              </FormField>
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">{t('Photo (optional)')}</legend>
            <p className="text-xs text-muted-foreground">
              {t('JPEG, PNG or WebP, up to 8 MB. Avoid showing faces of bystanders. Photos are never published.')}
            </p>
            <Button type="button" variant="outline" size="sm" onClick={() => photoInput.current?.click()}>
              <ImageUpIcon />
              {photo ? t('Choose a different photo') : t('Add a photo')}
            </Button>
            <input
              ref={photoInput}
              type="file"
              accept={ACCEPT_ATTRIBUTE}
              className="sr-only"
              tabIndex={-1}
              aria-label={t('Choose a photo')}
              onChange={(event) => void onPhoto(event)}
            />
            {photoError && (
              <p role="alert" className="text-sm font-medium text-destructive">
                {photoError}
              </p>
            )}
            {photo && (
              <figure className="flex items-center gap-3 rounded-lg border p-2">
                <img src={photo.previewUrl} alt={t('Selected photo')} className="size-16 rounded object-cover" />
                <figcaption className="min-w-0 flex-1 text-xs text-muted-foreground">
                  <p className="truncate">{photo.name}</p>
                  <p>{formatBytes(photo.size)}</p>
                </figcaption>
                <Button type="button" variant="ghost" size="icon" aria-label={t('Remove photo')} onClick={() => setPhoto(null)}>
                  <XIcon />
                </Button>
              </figure>
            )}
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-semibold">{t('Your identity')}</legend>
            {signedIn ? (
              <div className="space-y-2" role="radiogroup">
                {(
                  [
                    ['anonymous', 'Send without my account', 'No account is attached. Reviewers cannot contact you.'],
                    ['protected', 'Protected', 'Your account is stored with the report but hidden from reviewers and never published.'],
                    ['account', 'Linked to my account', 'Reviewers can see which account sent the report.'],
                  ] as const
                ).map(([value, label, help]) => (
                  <label key={value} className="flex items-start gap-3 rounded-lg border p-3 text-sm has-[:checked]:border-primary">
                    <input type="radio" value={value} className="mt-0.5 size-4 accent-primary" {...register('identity')} />
                    <span>
                      <span className="font-medium">{t(label)}</span>
                      <span className="block text-xs text-muted-foreground">{t(help)}</span>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {t('You are not signed in, so the report is sent without any account. Keep the reference number to check its progress.')}
              </p>
            )}
          </fieldset>

          <Alert variant="info">
            <ShieldCheckIcon />
            <AlertTitle>{t('How your report is handled')}</AlertTitle>
            <AlertDescription>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {PRIVACY_POINTS.map((point) => (
                  <li key={point}>{t(point)}</li>
                ))}
                <li>{t('A report is an allegation until reviewers verify it. Verification is not a legal or official finding.')}</li>
              </ul>
            </AlertDescription>
          </Alert>

          {formError && (
            <p role="alert" className="text-sm font-medium text-destructive">
              {formError}
            </p>
          )}
          <div className="flex justify-end">
            <Button type="submit" size="lg" disabled={isSubmitting}>
              {isSubmitting && <Spinner />}
              {isSubmitting ? t('Sending…') : t('Send report')}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function Confirmation({ outcome, onAnother }: { outcome: Outcome; onAnother: () => void }) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  if (outcome.kind === 'queued') {
    return (
      <Card>
        <CardContent className="space-y-4 pt-6">
          <Alert variant="warning">
            <WifiOffIcon />
            <AlertTitle>{t('Saved on this device, not yet sent')}</AlertTitle>
            <AlertDescription>
              {outcome.offline
                ? t('You are offline. The report will be sent automatically when you reconnect, and you will get a reference number then.')
                : t('The server could not be reached. The report will be retried automatically. Keep this page or the app open.')}
            </AlertDescription>
          </Alert>
          <Button onClick={onAnother}>{t('Report another incident')}</Button>
        </CardContent>
      </Card>
    )
  }
  return (
    <Card>
      <CardContent className="space-y-5 pt-6">
        <Alert variant="success">
          <CheckCircle2Icon />
          <AlertTitle>{t('Report received')}</AlertTitle>
          <AlertDescription>
            {t('Received {time}. It is listed as Reported until reviewers check it.', {
              time: dateFormatter.format(new Date(outcome.receivedAt)),
            })}
          </AlertDescription>
        </Alert>
        <div>
          <p className="text-sm text-muted-foreground">{t('Your reference number')}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <p className="font-mono text-2xl font-semibold tracking-wider" data-testid="incident-reference">
              {outcome.reference}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                void navigator.clipboard
                  ?.writeText(outcome.reference)
                  .then(() => setCopied(true))
                  .catch(() => setCopied(false))
              }
            >
              <CopyIcon />
              {copied ? t('Copied') : t('Copy')}
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('Write it down. It is the only way to check progress, because anonymous reports cannot be linked back to you.')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onAnother}>{t('Report another incident')}</Button>
          <Button asChild variant="outline">
            <Link to="/incidents">{t('See public incident summary')}</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function TrackReport() {
  const t = useT()
  const [input, setInput] = useState('')
  const [reference, setReference] = useState<string | null>(null)
  const track = useTrackIncident(reference)

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const value = input.trim().toUpperCase()
    setReference(value.length >= 6 ? value : null)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('Check a report')}</CardTitle>
        <CardDescription>{t('Enter the reference number you were given.')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={onSubmit} className="flex gap-2" role="search">
          <Input
            aria-label={t('Reference number')}
            placeholder="VV-XXXX-XXXX-XXXX"
            value={input}
            maxLength={24}
            autoComplete="off"
            onChange={(event) => setInput(event.target.value)}
          />
          <Button type="submit" variant="outline" size="icon" aria-label={t('Check')}>
            <SearchIcon />
          </Button>
        </form>
        {track.isFetching && <LoadingState label={t('Checking')} />}
        {track.isError && (
          <p role="alert" className="text-sm text-destructive">
            {track.error instanceof ApiError && track.error.status === 404
              ? t('No report has that reference. Check it and try again.')
              : t('The report could not be checked. Try again when you are online.')}
          </p>
        )}
        {track.data && (
          <div className="space-y-2 rounded-lg border p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs">{track.data.reference}</span>
              <BandBadge band={track.data.band} />
            </div>
            <p className="text-muted-foreground">{t(BAND_DESCRIPTIONS[track.data.band])}</p>
            <p className="text-xs text-muted-foreground">
              {t('Last updated {time}', { time: dateFormatter.format(new Date(track.data.last_updated_at)) })}
            </p>
            {track.data.public_summary && <p className="border-t pt-2">{track.data.public_summary}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function DeviceQueue() {
  const t = useT()
  const drafts = useIncidentDrafts()
  const remove = useDeleteIncidentDraft()
  const retry = useRetryIncidentDraft()
  const online = useOnlineStatus()

  if (drafts.isPending) return <LoadingState variant="skeleton" rows={2} label={t('Loading reports on this device')} />
  if (drafts.isError) {
    return <ErrorState message={t('Reports on this device could not be read.')} onRetry={() => void drafts.refetch()} />
  }
  if (drafts.data.length === 0) {
    return (
      <EmptyState
        icon={FileClockIcon}
        title={t('Nothing on this device')}
        description={t('Reports saved while offline wait here until they are sent.')}
      />
    )
  }

  return (
    <ul className="space-y-3" aria-label={t('Reports on this device')}>
      {drafts.data.map((draft) => {
        const legacy = isLegacyDraft(draft)
        const label = INCIDENT_CATEGORIES[draft.category as IncidentCategory] ?? draft.category
        return (
          <li key={draft.id} className="rounded-lg border bg-card p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium">{t(label)}</p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {draft.locationHint || t('No location')} · {dateFormatter.format(new Date(draft.occurredAt))}
                </p>
              </div>
              {legacy ? (
                <Badge variant="neutral">{t('Old draft')}</Badge>
              ) : draft.syncStatus === 'synced' ? (
                <Badge variant="success">{t('Sent')}</Badge>
              ) : draft.syncStatus === 'failed' ? (
                <Badge variant="destructive">{t('Not sent')}</Badge>
              ) : (
                <Badge variant="warning">{draft.syncStatus === 'syncing' ? t('Sending') : t('Waiting to send')}</Badge>
              )}
            </div>
            {draft.reference && <p className="mt-2 font-mono text-xs">{draft.reference}</p>}
            {legacy && (
              <p className="mt-2 text-xs text-muted-foreground">
                {t('Saved by an older version and cannot be sent. Re-enter it, then delete this copy.')}
              </p>
            )}
            {draft.syncStatus === 'queued' && !online && (
              <p className="mt-2 text-xs text-muted-foreground">{t('Will be sent when you reconnect.')}</p>
            )}
            {draft.lastError && draft.syncStatus !== 'synced' && (
              <p className="mt-2 text-xs text-destructive">{draft.lastError}</p>
            )}
            <div className="mt-2 flex gap-1">
              {draft.syncStatus === 'failed' && !legacy && (
                <Button variant="ghost" size="sm" onClick={() => retry.mutate(draft.id)} disabled={!online}>
                  <RotateCcwIcon />
                  {t('Retry')}
                </Button>
              )}
              {draft.syncStatus !== 'syncing' && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  aria-label={draft.syncStatus === 'synced' ? t('Remove from this device') : t('Delete report')}
                  onClick={() => remove.mutate(draft.id)}
                >
                  <Trash2Icon />
                  {draft.syncStatus === 'synced' ? t('Remove') : t('Delete')}
                </Button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function ReportIncidentPage() {
  const t = useT()
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [formKey, setFormKey] = useState(0)

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t('Incident reporting')}
        title={t('Report an incident')}
        description={t('Reviewers check every report before anything is published.')}
      />

      <Alert variant="warning">
        <PhoneCallIcon />
        <AlertTitle>{t('In danger? Get help first')}</AlertTitle>
        <AlertDescription>
          {t('VoteTrace cannot send help. Call the police or emergency services.')}
        </AlertDescription>
      </Alert>

      <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
        <div>
          {outcome ? (
            <Confirmation
              outcome={outcome}
              onAnother={() => {
                setOutcome(null)
                setFormKey((key) => key + 1)
              }}
            />
          ) : (
            <IncidentReportForm key={formKey} onDone={setOutcome} />
          )}
        </div>
        <aside className="space-y-6">
          <TrackReport />
          <section aria-labelledby="device-queue-heading">
            <h2 id="device-queue-heading" className="mb-3 text-sm font-semibold">
              {t('On this device')}
            </h2>
            <DeviceQueue />
          </section>
        </aside>
      </div>
    </div>
  )
}
