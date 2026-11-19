import { CameraIcon, FingerprintIcon, ImageUpIcon, SaveIcon, ShieldCheckIcon, XIcon } from 'lucide-react'
import { useEffect, useId, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { describedBy, FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/input'
import { usePollingUnitSearch } from '@/features/directory/api'
import { DataSourceNotice } from '@/features/directory/data-notice'
import { LocationSelect, type LocationValue } from '@/features/directory/location-select'
import { useElections } from '@/features/evidence/api'
import { saveDraft, syncEvidence } from '@/features/evidence/evidence-queue'
import { formatBytes, prepareEvidencePhoto, sha256Hex } from '@/features/evidence/file-checks'
import { cn } from '@/lib/utils'
import { useT } from '@/i18n/locale-provider'

type Photo = {
  fileName: string
  byteSize: number
  data: ArrayBuffer
  type: string
  sha256: string
  previewUrl: string
  source: 'camera' | 'upload'
  capturedAt: string
}

/** Device time the photo was taken or chosen. Clamped so a wrong file date cannot be in the future. */
function captureTime(file: File) {
  const now = Date.now()
  return new Date(file.lastModified > 0 && file.lastModified <= now ? file.lastModified : now).toISOString()
}

export function SubmitEvidencePage() {
  const t = useT()
  const navigate = useNavigate()
  const formId = useId()
  const elections = useElections()
  const [electionId, setElectionId] = useState('')
  const [location, setLocation] = useState<LocationValue>({})
  const [pollingUnitId, setPollingUnitId] = useState('')
  const [photo, setPhoto] = useState<Photo | null>(null)
  const [fileError, setFileError] = useState<string>()
  const [formError, setFormError] = useState<string>()
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)

  const units = usePollingUnitSearch({ wardId: location.wardId, pageSize: 50 }, Boolean(location.wardId))
  const electionList = elections.data?.data.items ?? []
  const election = electionList.find((item) => item.id === electionId)
  const unit = units.data?.data.items.find((item) => item.id === pollingUnitId)

  useEffect(() => () => (photo ? URL.revokeObjectURL(photo.previewUrl) : undefined), [photo])

  async function onFile(event: ChangeEvent<HTMLInputElement>, source: Photo['source']) {
    const input = event.currentTarget
    const file = input.files?.[0]
    // Read the bytes before clearing the input. On iPhone, resetting the input first
    // drops the camera file and the photo can no longer be found.
    if (!file) {
      setFileError('No photo came back from the camera. Take it again.')
      return
    }
    setFileError(undefined)
    setChecking(true)
    try {
      const prepared = await prepareEvidencePhoto(file)
      if (!prepared.ok) {
        setFileError(prepared.message)
        return
      }
      const preview = new Blob([prepared.data], { type: prepared.type })
      // Fingerprint the exact bytes now; the server recomputes it and refuses a mismatch.
      const sha256 = await sha256Hex(prepared.data)
      setPhoto({
        fileName: prepared.fileName,
        byteSize: prepared.data.byteLength,
        data: prepared.data,
        type: prepared.type,
        sha256,
        previewUrl: URL.createObjectURL(preview),
        source,
        capturedAt: captureTime(file),
      })
    } catch {
      setFileError('The photo could not be read. Take it again.')
    } finally {
      input.value = ''
      setChecking(false)
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!election || !unit || !photo) {
      setFormError('Choose the election and polling unit, and add a photo of the result sheet.')
      return
    }
    setFormError(undefined)
    setSaving(true)
    try {
      await saveDraft({
        electionId: election.id,
        electionName: election.name,
        pollingUnitId: unit.id,
        pollingUnitCode: unit.code,
        pollingUnitName: unit.name,
        fileName: photo.fileName,
        contentType: photo.type,
        data: photo.data,
        byteSize: photo.data.byteLength,
        sha256: photo.sha256,
        captureSource: photo.source,
        capturedAt: photo.capturedAt,
      })
      if (navigator.onLine) void syncEvidence()
      navigate('/evidence', { state: { saved: true } })
    } catch {
      setFormError('The photo could not be saved on this device. Free some storage space and try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        eyebrow={t('Field evidence')}
        title={t('Submit a result sheet')}
        description={t('Saved on this device first, then uploaded when you are online.')}
        actions={
          <Button asChild variant="outline">
            <Link to="/evidence">{t('My submissions')}</Link>
          </Button>
        }
      />

      {elections.data && <DataSourceNotice source={elections.data.data.data_source} />}

      <form id={formId} onSubmit={onSubmit} className="space-y-6" noValidate>
        <Card>
          <CardHeader>
            <CardTitle>1. Election and polling unit</CardTitle>
            <CardDescription>Select exactly where this result sheet comes from.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField id="evidence-election" label="Election" required>
              <Select
                id="evidence-election"
                value={electionId}
                onChange={(event) => setElectionId(event.target.value)}
                disabled={elections.isPending}
              >
                <option value="">{elections.isPending ? 'Loading elections…' : 'Choose an election'}</option>
                {electionList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <LocationSelect
              idPrefix="evidence-location"
              value={location}
              onChange={(next) => {
                setLocation(next)
                setPollingUnitId('')
              }}
            />
            <FormField id="evidence-polling-unit" label="Polling unit" required>
              <Select
                id="evidence-polling-unit"
                value={pollingUnitId}
                disabled={!location.wardId || units.isPending}
                onChange={(event) => setPollingUnitId(event.target.value)}
              >
                <option value="">{location.wardId ? 'Choose a polling unit' : 'Choose a ward first'}</option>
                {units.data?.data.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.code} · {item.name}
                  </option>
                ))}
              </Select>
            </FormField>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>2. Photo of the result sheet</CardTitle>
            <CardDescription>
              Capture the whole sheet, flat and well lit, with every figure readable. JPEG, PNG or WebP, up to 15 MB.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:flex sm:flex-wrap">
              <label className={cn(buttonVariants(), 'relative h-auto min-h-10 w-full cursor-pointer whitespace-normal py-2 sm:w-auto', checking && 'pointer-events-none opacity-50')}>
                <CameraIcon />
                Take photo
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  disabled={checking}
                  aria-label="Take photo with camera"
                  className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                  onChange={(event) => void onFile(event, 'camera')}
                />
              </label>
              <label
                className={cn(
                  buttonVariants({ variant: 'outline' }),
                  'relative h-auto min-h-10 w-full cursor-pointer whitespace-normal py-2 sm:w-auto',
                  checking && 'pointer-events-none opacity-50',
                )}
              >
                <ImageUpIcon />
                Choose existing photo
                <input
                  type="file"
                  accept="image/*"
                  disabled={checking}
                  aria-label="Choose photo file"
                  aria-describedby={describedBy('evidence-file', fileError)}
                  className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                  onChange={(event) => void onFile(event, 'upload')}
                />
              </label>
            </div>
            {checking && <p className="text-sm text-muted-foreground">Checking photo…</p>}
            {fileError && (
              <p id="evidence-file-error" role="alert" className="text-sm font-medium text-destructive">
                {fileError}
              </p>
            )}
            {photo && (
              <figure className="space-y-3">
                <div className="overflow-hidden rounded-lg border bg-muted">
                  <img
                    src={photo.previewUrl}
                    alt="Preview of the selected result sheet photo"
                    className="max-h-[28rem] w-full object-contain"
                  />
                </div>
                <figcaption className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    {photo.fileName} · {formatBytes(photo.byteSize)} ·{' '}
                    {photo.source === 'camera' ? 'taken with camera' : 'chosen from device'}
                  </p>
                  <p className="flex items-center gap-1 break-all">
                    <FingerprintIcon className="size-3.5 shrink-0" aria-hidden />
                    SHA-256 {photo.sha256}
                  </p>
                </figcaption>
                <Button type="button" variant="ghost" size="sm" onClick={() => setPhoto(null)}>
                  <XIcon />
                  Remove photo
                </Button>
              </figure>
            )}
          </CardContent>
        </Card>

        <Alert variant="info">
          <ShieldCheckIcon />
          <AlertTitle>What happens next</AlertTitle>
          <AlertDescription>
            The original photo is kept unchanged and fingerprinted. Figures are read by OCR, checked for consistency and
            compared with other submissions, then reviewed by trained people. Nothing is treated as verified
            automatically, and VoteTrace statuses are not INEC declarations.
          </AlertDescription>
        </Alert>

        {formError && (
          <p role="alert" className="text-sm font-medium text-destructive">
            {formError}
          </p>
        )}
        <div className="flex sm:justify-end">
          <Button type="submit" size="lg" className="w-full sm:w-auto" disabled={saving || checking}>
            <SaveIcon />
            {saving ? 'Saving…' : 'Save and submit'}
          </Button>
        </div>
      </form>
    </div>
  )
}
