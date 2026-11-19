import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarPlusIcon,
  FileUpIcon,
  MapPinIcon,
  MegaphoneIcon,
  PlusIcon,
  TrashIcon,
  VoteIcon,
} from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { PUBLIC_QUERY_KEY } from '@/features/directory/api'
import {
  UPDATE_CATEGORIES,
  UPDATE_VERIFICATION_STATUSES,
  type UpdateCategory,
  type UpdateVerificationStatus,
} from '@/features/directory/types'
import { UPDATE_CATEGORY_LABEL, UPDATE_VERIFICATION_META } from '@/features/updates/status'
import { useT } from '@/i18n/locale-provider'
import { api, ApiError } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type ImportReport = {
  applied: boolean
  rows: number
  states_created: number
  lgas_created: number
  wards_created: number
  units_created: number
  units_updated: number
  units_unchanged: number
  error_count: number
  errors: { row: number; message: string }[]
  sha256: string
}

type RegisterSummary = {
  states: number
  lgas: number
  wards: number
  polling_units: number
  with_coordinates: number
  imports: { id: string; imported_at: string; actor_email: string | null; details: Record<string, unknown> }[]
}

type Party = { code: string; name: string }
type ElectionStatus = 'scheduled' | 'active' | 'closed'
type AdminElection = {
  election: {
    id: string
    name: string
    election_label: string
    election_date: string
    template_id: string
    parties: Party[]
  }
  status: ElectionStatus
  submissions: number
}
type Template = { id: string; name: string; notice: string }

const REGISTER_KEY = ['admin', 'register'] as const
const ELECTIONS_KEY = ['admin', 'elections'] as const
const STATUS_LABEL: Record<ElectionStatus, string> = { scheduled: 'Scheduled', active: 'Active', closed: 'Closed' }

function errorText(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="text-sm font-medium text-destructive">
      {message}
    </p>
  )
}

function ImportResult({ report }: { report: ImportReport }) {
  const t = useT()
  if (report.error_count > 0) {
    return (
      <Alert variant="destructive" role="status">
        <AlertTitle>{t('Rejected: {count} problem(s). Nothing was imported.', { count: report.error_count })}</AlertTitle>
        <AlertDescription>
          <ul className="mt-2 max-h-64 list-disc space-y-1 overflow-y-auto pl-5">
            {report.errors.map((error) => (
              <li key={`${error.row}-${error.message}`}>
                {t('Row {row}', { row: error.row })}: {error.message}
              </li>
            ))}
          </ul>
          {report.error_count > report.errors.length && (
            <p className="mt-2">{t('Only the first {count} problems are listed.', { count: report.errors.length })}</p>
          )}
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <Alert variant={report.applied ? 'success' : 'info'} role="status">
      <AlertTitle>
        {report.applied
          ? t('Imported {rows} rows', { rows: report.rows })
          : t('Checked {rows} rows. The file is valid and nothing was written yet.', { rows: report.rows })}
      </AlertTitle>
      <AlertDescription>
        {t(
          '{states} states, {lgas} LGAs, {wards} wards and {units} polling units new; {updated} updated; {unchanged} unchanged.',
          {
            states: report.states_created,
            lgas: report.lgas_created,
            wards: report.wards_created,
            units: report.units_created,
            updated: report.units_updated,
            unchanged: report.units_unchanged,
          },
        )}
      </AlertDescription>
    </Alert>
  )
}

function RegisterSection() {
  const t = useT()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState('')
  const [reference, setReference] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const summary = useQuery({ queryKey: REGISTER_KEY, queryFn: () => api.get<RegisterSummary>('/admin/register') })

  const upload = useMutation({
    mutationFn: (dryRun: boolean) => {
      const body = new FormData()
      body.set('file', file as File)
      body.set('source_name', source.trim())
      if (reference.trim()) body.set('source_reference', reference.trim())
      body.set('dry_run', String(dryRun))
      return api.post<ImportReport>('/admin/register/import', body)
    },
    onSuccess: (result) => {
      setReport(result)
      if (result.applied) {
        void queryClient.invalidateQueries({ queryKey: REGISTER_KEY })
        void queryClient.invalidateQueries({ queryKey: [PUBLIC_QUERY_KEY] })
      }
    },
    onError: (err) => setError(errorText(err, t('The file could not be uploaded.'))),
  })

  const submit = (dryRun: boolean) => (event?: FormEvent) => {
    event?.preventDefault()
    setError(null)
    setReport(null)
    if (!file) return setError(t('Choose the CSV file to import.'))
    if (source.trim().length < 3) return setError(t('Name the source of this register, for example the INEC publication.'))
    upload.mutate(dryRun)
  }

  const counts = summary.data
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <MapPinIcon className="size-4 text-primary" aria-hidden />
            {t('Polling-unit register')}
          </CardTitle>
          <CardDescription>{t('What the public finder, evidence capture, results and USSD and SMS currently use.')}</CardDescription>
        </CardHeader>
        <CardContent>
          {summary.isPending ? (
            <LoadingState className="py-6" />
          ) : summary.isError ? (
            <ErrorState
              message={errorText(summary.error, t('The register could not be loaded.'))}
              onRetry={() => void summary.refetch()}
            />
          ) : (
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              {[
                [t('States'), counts!.states],
                [t('LGAs'), counts!.lgas],
                [t('Wards'), counts!.wards],
                [t('Polling units'), counts!.polling_units],
                [t('With coordinates'), counts!.with_coordinates],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border p-3">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="text-xl font-semibold tabular-nums">{Number(value).toLocaleString()}</dd>
                </div>
              ))}
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileUpIcon className="size-4 text-primary" aria-hidden />
            {t('Import from CSV')}
          </CardTitle>
          <CardDescription>
            {t('Use the official INEC polling-unit list. Required columns: state, lga, ward, polling_unit_code, polling_unit_name. Optional: address, latitude, longitude, registered_voters. Units are matched by code, so re-importing a corrected file updates them in place. One bad row rejects the whole file.')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit(false)} noValidate className="space-y-4">
            <FormField id="register-file" label={t('CSV file')} required>
              <Input
                ref={fileInput}
                id="register-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null)
                  setReport(null)
                }}
              />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="register-source" label={t('Source')} required>
                <Input
                  id="register-source"
                  placeholder={t('For example: INEC polling units, 2023 general election')}
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                />
              </FormField>
              <FormField id="register-reference" label={t('Reference or link')}>
                <Input id="register-reference" value={reference} onChange={(event) => setReference(event.target.value)} />
              </FormField>
            </div>
            <ErrorLine message={error} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" disabled={upload.isPending} onClick={() => submit(true)()}>
                {upload.isPending && upload.variables === true && <Spinner />}
                {t('Check file')}
              </Button>
              <Button type="submit" disabled={upload.isPending}>
                {upload.isPending && upload.variables === false ? <Spinner /> : <FileUpIcon />}
                {t('Import')}
              </Button>
            </div>
          </form>
          {report && (
            <div className="mt-4">
              <ImportResult report={report} />
            </div>
          )}
        </CardContent>
      </Card>

      {counts && counts.imports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('Import history')}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y text-sm">
              {counts.imports.map((record) => (
                <li key={record.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-medium">{String(record.details.source_name ?? '')}</p>
                    <p className="text-muted-foreground">
                      {t('{rows} rows, {created} new, {updated} updated', {
                        rows: Number(record.details.rows ?? 0),
                        created: Number(record.details.units_created ?? 0),
                        updated: Number(record.details.units_updated ?? 0),
                      })}
                      {' · '}
                      {record.actor_email ?? t('command line')}
                    </p>
                  </div>
                  <time className="text-muted-foreground" dateTime={record.imported_at}>
                    {new Date(record.imported_at).toLocaleString()}
                  </time>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

type ElectionDraft = {
  name: string
  election_label: string
  election_date: string
  template_id: string
  status: ElectionStatus
  parties: Party[]
}

const EMPTY_DRAFT: ElectionDraft = {
  name: '',
  election_label: '',
  election_date: '',
  template_id: '',
  status: 'scheduled',
  parties: [{ code: '', name: '' }],
}

function ElectionForm({
  initial,
  templates,
  locked,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: ElectionDraft
  templates: Template[]
  locked: boolean
  submitLabel: string
  pending: boolean
  error: string | null
  onSubmit: (draft: ElectionDraft) => void
  onCancel?: () => void
}) {
  const t = useT()
  const [draft, setDraft] = useState<ElectionDraft>({
    ...initial,
    template_id: initial.template_id || templates[0]?.id || '',
  })
  const [problem, setProblem] = useState<string | null>(null)
  const set = <K extends keyof ElectionDraft>(key: K, value: ElectionDraft[K]) => setDraft((d) => ({ ...d, [key]: value }))
  const setParty = (index: number, patch: Partial<Party>) =>
    set(
      'parties',
      draft.parties.map((party, i) => (i === index ? { ...party, ...patch } : party)),
    )
  const id = initial.name ? 'edit' : 'new'

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setProblem(null)
    const parties = draft.parties
      .map((p) => ({ code: p.code.trim().toUpperCase(), name: p.name.trim() }))
      .filter((p) => p.code || p.name)
    if (draft.name.trim().length < 3) return setProblem(t('Enter the election name.'))
    if (draft.election_label.trim().length < 2) return setProblem(t('Enter the label printed on the result sheet.'))
    if (!draft.election_date) return setProblem(t('Choose the election date.'))
    if (parties.length === 0) return setProblem(t('Add at least one party on the ballot.'))
    if (parties.some((p) => !/^[A-Z0-9]{1,12}$/.test(p.code) || !p.name))
      return setProblem(t('Each party needs a code (letters and digits, up to 12) and a name.'))
    if (new Set(parties.map((p) => p.code)).size !== parties.length) return setProblem(t('Party codes must be unique.'))
    onSubmit({ ...draft, parties })
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id={`${id}-name`} label={t('Election name')} required>
          <Input id={`${id}-name`} value={draft.name} onChange={(e) => set('name', e.target.value)} />
        </FormField>
        <FormField id={`${id}-label`} label={t('Label on the result sheet')} required>
          <Input
            id={`${id}-label`}
            placeholder="PRESIDENTIAL"
            disabled={locked}
            value={draft.election_label}
            onChange={(e) => set('election_label', e.target.value)}
          />
        </FormField>
        <FormField id={`${id}-date`} label={t('Election date')} required>
          <Input id={`${id}-date`} type="date" value={draft.election_date} onChange={(e) => set('election_date', e.target.value)} />
        </FormField>
        <FormField id={`${id}-status`} label={t('Status')}>
          <Select id={`${id}-status`} value={draft.status} onChange={(e) => set('status', e.target.value as ElectionStatus)}>
            {(Object.keys(STATUS_LABEL) as ElectionStatus[]).map((status) => (
              <option key={status} value={status}>
                {t(STATUS_LABEL[status])}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id={`${id}-template`} label={t('Result-sheet template')} required>
          <Select
            id={`${id}-template`}
            disabled={locked}
            value={draft.template_id}
            onChange={(e) => set('template_id', e.target.value)}
          >
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </Select>
        </FormField>
      </div>
      <fieldset className="space-y-2" disabled={locked}>
        <legend className="text-sm font-medium">{t('Parties on the ballot, in ballot order')}</legend>
        {draft.parties.map((party, index) => (
          <div key={index} className="flex gap-2">
            <Input
              aria-label={t('Party code')}
              placeholder={t('Code')}
              className="w-28 uppercase"
              value={party.code}
              onChange={(e) => setParty(index, { code: e.target.value })}
            />
            <Input
              aria-label={t('Party name')}
              placeholder={t('Full party name')}
              value={party.name}
              onChange={(e) => setParty(index, { name: e.target.value })}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={t('Remove party')}
              disabled={draft.parties.length === 1}
              onClick={() => set('parties', draft.parties.filter((_, i) => i !== index))}
            >
              <TrashIcon />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={draft.parties.length >= 40}
          onClick={() => set('parties', [...draft.parties, { code: '', name: '' }])}
        >
          <PlusIcon />
          {t('Add party')}
        </Button>
        {locked && (
          <p className="text-xs text-muted-foreground">
            {t('Evidence has been submitted for this election, so its sheet label, template and parties are locked.')}
          </p>
        )}
      </fieldset>
      <ErrorLine message={problem ?? error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending && <Spinner />}
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t('Cancel')}
          </Button>
        )}
      </div>
    </form>
  )
}

function ElectionRow({ item, templates }: { item: AdminElection; templates: Template[] }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const locked = item.submissions > 0
  const save = useMutation({
    mutationFn: (draft: ElectionDraft) =>
      api.patch<AdminElection>(
        `/admin/elections/${item.election.id}`,
        locked
          ? { name: draft.name, election_date: draft.election_date, status: draft.status }
          : draft,
      ),
    onSuccess: () => {
      setEditing(false)
      void queryClient.invalidateQueries({ queryKey: ELECTIONS_KEY })
      void queryClient.invalidateQueries({ queryKey: [PUBLIC_QUERY_KEY] })
    },
    onError: (err) => setError(errorText(err, t('The election could not be saved.'))),
  })
  const { election } = item
  return (
    <li className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{election.name}</p>
          <p className="text-sm text-muted-foreground">
            {new Date(`${election.election_date}T00:00:00`).toLocaleDateString()} · {election.election_label} ·{' '}
            {t('{count} evidence submissions', { count: item.submissions })}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant={item.status === 'active' ? 'success' : 'neutral'}>{t(STATUS_LABEL[item.status])}</Badge>
            {election.parties.map((party) => (
              <Badge key={party.code} variant="outline" title={party.name}>
                {party.code}
              </Badge>
            ))}
          </div>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => setEditing((open) => !open)}>
          {editing ? t('Close') : t('Edit')}
        </Button>
      </div>
      {editing && (
        <div className="rounded-md border bg-muted/30 p-4">
          <ElectionForm
            initial={{ ...election, status: item.status }}
            templates={templates}
            locked={locked}
            submitLabel={t('Save changes')}
            pending={save.isPending}
            error={error}
            onSubmit={(draft) => {
              setError(null)
              save.mutate(draft)
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </li>
  )
}

function ElectionsSection() {
  const t = useT()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const elections = useQuery({ queryKey: ELECTIONS_KEY, queryFn: () => api.get<AdminElection[]>('/admin/elections') })
  const templates = useQuery({
    queryKey: ['admin', 'election-templates'],
    queryFn: () => api.get<Template[]>('/admin/election-templates'),
  })
  const create = useMutation({
    mutationFn: (draft: ElectionDraft) => api.post<AdminElection>('/admin/elections', draft),
    onSuccess: () => {
      setCreating(false)
      setFormKey((key) => key + 1)
      void queryClient.invalidateQueries({ queryKey: ELECTIONS_KEY })
      void queryClient.invalidateQueries({ queryKey: [PUBLIC_QUERY_KEY] })
    },
    onError: (err) => setError(errorText(err, t('The election could not be created.'))),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <VoteIcon className="size-4 text-primary" aria-hidden />
              {t('Elections')}
            </CardTitle>
            <CardDescription>
              {t('Evidence is captured against these elections, and results, USSD and SMS answer for the latest one. Use the parties and sheet label from the official ballot.')}
            </CardDescription>
          </div>
          {!creating && (
            <Button type="button" onClick={() => setCreating(true)} disabled={!templates.data}>
              <CalendarPlusIcon />
              {t('New election')}
            </Button>
          )}
        </CardHeader>
        {creating && templates.data && (
          <CardContent>
            <div className="rounded-md border p-4">
              <ElectionForm
                key={formKey}
                initial={EMPTY_DRAFT}
                templates={templates.data}
                locked={false}
                submitLabel={t('Create election')}
                pending={create.isPending}
                error={error}
                onSubmit={(draft) => {
                  setError(null)
                  create.mutate(draft)
                }}
                onCancel={() => setCreating(false)}
              />
            </div>
          </CardContent>
        )}
      </Card>
      <Card>
        <CardContent className="p-0">
          {elections.isPending || templates.isPending ? (
            <LoadingState className="py-10" />
          ) : elections.isError ? (
            <ErrorState
              message={errorText(elections.error, t('Elections could not be loaded.'))}
              onRetry={() => void elections.refetch()}
            />
          ) : elections.data.length === 0 ? (
            <EmptyState
              icon={VoteIcon}
              title={t('No elections yet')}
              description={t('Create the election you are observing before field staff submit evidence.')}
            />
          ) : (
            <ul className="divide-y">
              {elections.data.map((item) => (
                <ElectionRow key={item.election.id} item={item} templates={templates.data ?? []} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function UpdatesSection() {
  const t = useT()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<UpdateCategory>('general_information')
  const [status, setStatus] = useState<UpdateVerificationStatus>('reported_unverified')
  const [sourceName, setSourceName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [reference, setReference] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [published, setPublished] = useState<string | null>(null)

  const publish = useMutation({
    mutationFn: () =>
      api.post<{ item: { id: string; title: string } }>('/admin/updates', {
        title: title.trim(),
        description: description.trim(),
        category,
        verification_status: status,
        source_name: sourceName.trim(),
        source_url: sourceUrl.trim() || null,
        reference: reference.trim() || null,
      }),
    onSuccess: (data) => {
      setPublished(data.item.title)
      setTitle('')
      setDescription('')
      setSourceUrl('')
      setReference('')
      void queryClient.invalidateQueries({ queryKey: [PUBLIC_QUERY_KEY] })
    },
    onError: (err) => setError(errorText(err, t('The update could not be published.'))),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setPublished(null)
    if (title.trim().length < 5) return setError(t('The title needs at least 5 characters.'))
    if (description.trim().length < 10) return setError(t('The description needs at least 10 characters.'))
    if (sourceName.trim().length < 2) return setError(t('Name the source of this update.'))
    if (sourceUrl.trim() && !sourceUrl.trim().startsWith('https://')) return setError(t('Links must start with https://'))
    if (status === 'officially_confirmed' && !sourceUrl.trim() && !reference.trim())
      return setError(t('Officially confirmed updates need a reference or a link to the original.'))
    publish.mutate()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MegaphoneIcon className="size-4 text-primary" aria-hidden />
          {t('Publish an update')}
        </CardTitle>
        <CardDescription>
          {t('Appears on the public Updates page and in USSD and SMS. Label it honestly: only mark it officially confirmed when a named authority published it.')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="space-y-4">
          <FormField id="update-title" label={t('Title')} required>
            <Input id="update-title" maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} />
          </FormField>
          <FormField id="update-description" label={t('Details')} required>
            <Textarea
              id="update-description"
              rows={4}
              maxLength={4000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="update-category" label={t('Category')}>
              <Select id="update-category" value={category} onChange={(e) => setCategory(e.target.value as UpdateCategory)}>
                {UPDATE_CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {t(UPDATE_CATEGORY_LABEL[value])}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="update-status" label={t('Verification')}>
              <Select
                id="update-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as UpdateVerificationStatus)}
              >
                {UPDATE_VERIFICATION_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {t(UPDATE_VERIFICATION_META[value].label)}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="update-source" label={t('Source')} required>
              <Input id="update-source" value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
            </FormField>
            <FormField id="update-reference" label={t('Reference')}>
              <Input id="update-reference" value={reference} onChange={(e) => setReference(e.target.value)} />
            </FormField>
          </div>
          <FormField id="update-url" label={t('Link to the original (https)')}>
            <Input id="update-url" type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          </FormField>
          <ErrorLine message={error} />
          {published && (
            <p role="status" className="text-sm font-medium text-success">
              {t('Published: {title}', { title: published })}
            </p>
          )}
          <Button type="submit" disabled={publish.isPending}>
            {publish.isPending ? <Spinner /> : <MegaphoneIcon />}
            {t('Publish update')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

const TABS = [
  { id: 'register', label: 'Polling-unit register' },
  { id: 'elections', label: 'Elections' },
  { id: 'updates', label: 'Updates' },
] as const
type Tab = (typeof TABS)[number]['id']

export function RegisterPage() {
  const t = useT()
  const [tab, setTab] = useState<Tab>('register')
  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Elections and register')}
        description={t('Polling-unit list, elections and updates. Every change is logged.')}
      />
      <div role="tablist" aria-label={t('Sections')} className="flex flex-wrap gap-2 border-b">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              tab === item.id
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t(item.label)}
          </button>
        ))}
      </div>
      {tab === 'register' && <RegisterSection />}
      {tab === 'elections' && <ElectionsSection />}
      {tab === 'updates' && <UpdatesSection />}
    </div>
  )
}
