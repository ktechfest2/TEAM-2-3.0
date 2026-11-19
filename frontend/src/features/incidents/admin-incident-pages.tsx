import {
  ArrowLeftIcon,
  CopyIcon,
  ImageIcon,
  ListChecksIcon,
  MapPinIcon,
  RotateCcwIcon,
  ShieldAlertIcon,
  SirenIcon,
} from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { describedBy, FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { LocationSelect } from '@/features/directory/location-select'
import { useElections } from '@/features/evidence/api'
import {
  useIncident,
  useIncidentAttachment,
  useIncidentList,
  useIncidentStats,
  useReviewIncident,
} from '@/features/incidents/api'
import { BandBadge, SeverityBadge, StatusBadge } from '@/features/incidents/badges'
import {
  INCIDENT_CATEGORIES,
  INCIDENT_SEVERITIES,
  INCIDENT_STATUSES,
  type CountItem,
  type IncidentAttachment,
  type IncidentCategory,
  type IncidentDetail,
  type IncidentFilters,
  type IncidentSeverity,
  type IncidentStatus,
  type IncidentSummary,
} from '@/features/incidents/types'
import { useT } from '@/i18n/locale-provider'
import { ApiError } from '@/lib/api-client'

const dateTime = new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium', timeStyle: 'short' })
const ALLEGATION_NOTICE =
  'Reports are allegations from the public until reviewers verify them. Do not share report content, reporter details or photos outside the review team.'

function when(value: string, approximate = false) {
  return `${approximate ? '~ ' : ''}${dateTime.format(new Date(value))}`
}

function startOfDay(date: string) {
  return date ? new Date(`${date}T00:00:00`).toISOString() : undefined
}

function endOfDay(date: string) {
  return date ? new Date(`${date}T23:59:59`).toISOString() : undefined
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

function StatCard({ title, value, detail, tone }: { title: string; value: number; detail: string; tone?: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone ?? ''}`}>{value.toLocaleString('en-NG')}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  )
}

function Bars({ title, items, empty }: { title: string; items: { key: string; label: string; count: number }[]; empty: string }) {
  const t = useT()
  const max = Math.max(1, ...items.map((item) => item.count))
  const shown = items.filter((item) => item.count > 0)
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="space-y-2">
            {shown.map((item) => (
              <li key={item.key} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{t(item.label)}</span>
                  <span className="tabular-nums text-muted-foreground">{item.count}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-muted" aria-hidden>
                  <div className="h-1.5 rounded-full bg-primary" style={{ width: `${(item.count / max) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function Timeline({ points, bucket }: { points: { period: string; count: number }[]; bucket: 'hour' | 'day' }) {
  const t = useT()
  const max = Math.max(1, ...points.map((point) => point.count))
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{t('Timeline of reported incidents')}</CardTitle>
        <CardDescription>{bucket === 'hour' ? t('Reports per hour, by time of incident') : t('Reports per day, by time of incident')}</CardDescription>
      </CardHeader>
      <CardContent>
        {points.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('No reports in this period.')}</p>
        ) : (
          <ol className="flex h-32 items-end gap-1" aria-label={t('Timeline')}>
            {points.map((point) => (
              <li
                key={point.period}
                className="min-w-1 flex-1 rounded-t bg-primary/80"
                style={{ height: `${Math.max(4, (point.count / max) * 100)}%` }}
                title={`${point.period}: ${point.count}`}
              >
                <span className="sr-only">
                  {point.period}: {point.count}
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

function IncidentRows({ items }: { items: IncidentSummary[] }) {
  const t = useT()
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[48rem] text-sm">
        <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">{t('Reference')}</th>
            <th className="px-3 py-2 font-medium">{t('Category')}</th>
            <th className="px-3 py-2 font-medium">{t('Severity')}</th>
            <th className="px-3 py-2 font-medium">{t('Status')}</th>
            <th className="px-3 py-2 font-medium">{t('Location')}</th>
            <th className="px-3 py-2 font-medium">{t('Occurred')}</th>
            <th className="px-3 py-2 font-medium">{t('Indicators')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-t align-top">
              <td className="px-3 py-2">
                <Link to={`/admin/incidents/${item.id}`} className="font-mono text-xs font-medium text-primary hover:underline">
                  {item.reference}
                </Link>
              </td>
              <td className="px-3 py-2">
                {t(INCIDENT_CATEGORIES[item.category])}
                {item.category !== item.reported_category && (
                  <span className="block text-xs text-muted-foreground">{t('Reclassified')}</span>
                )}
              </td>
              <td className="px-3 py-2">
                <SeverityBadge severity={item.severity} />
              </td>
              <td className="px-3 py-2">
                <StatusBadge status={item.status} />
              </td>
              <td className="px-3 py-2 text-xs">
                {item.lga.name}, {item.state.name}
                {item.polling_unit?.code && <span className="block text-muted-foreground">{item.polling_unit.code}</span>}
              </td>
              <td className="px-3 py-2 text-xs">{when(item.occurred_at, item.time_is_approximate)}</td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1">
                  {item.possible_duplicate_of && <Badge variant="warning">{t('Possible duplicate')}</Badge>}
                  {item.similar_count > 0 && (
                    <Badge variant="info">{t('{count} similar', { count: item.similar_count })}</Badge>
                  )}
                  {item.has_attachment && (
                    <Badge variant="neutral">
                      <ImageIcon />
                      {t('Photo')}
                    </Badge>
                  )}
                  {item.is_public && <Badge variant="success">{t('Published')}</Badge>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Pager({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  const t = useT()
  if (totalPages <= 1) return null
  return (
    <nav aria-label={t('Pagination')} className="flex items-center justify-between text-sm">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        {t('Previous')}
      </Button>
      <span>{t('Page {page} of {total}', { page, total: totalPages })}</span>
      <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        {t('Next')}
      </Button>
    </nav>
  )
}

function IncidentListing({ filters, queue }: { filters: IncidentFilters; queue: boolean }) {
  const t = useT()
  const [page, setPage] = useState(1)
  const list = useIncidentList(filters, page, queue)
  if (list.isPending) return <LoadingState variant="skeleton" label={t('Loading reports')} />
  if (list.isError) return <ErrorState message={errorMessage(list.error, t('Reports could not be loaded.'))} onRetry={() => void list.refetch()} />
  if (list.data.items.length === 0) {
    return (
      <EmptyState
        icon={SirenIcon}
        title={queue ? t('The review queue is empty') : t('No reports match these filters')}
        description={queue ? t('New and open reports appear here, most severe first.') : t('Try widening the filters.')}
      />
    )
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {queue ? t('{count} open report(s), most severe and oldest first', { count: list.data.total }) : t('{count} report(s)', { count: list.data.total })}
      </p>
      <IncidentRows items={list.data.items} />
      <Pager page={list.data.page} totalPages={list.data.total_pages} onPage={setPage} />
    </div>
  )
}

const EMPTY_FILTERS = {
  electionId: '',
  stateId: '',
  lgaId: '',
  wardId: '',
  category: '',
  severity: '',
  status: '',
  from: '',
  to: '',
}

export function IncidentDashboardPage() {
  const t = useT()
  const elections = useElections()
  const [form, setForm] = useState(EMPTY_FILTERS)
  const [queue, setQueue] = useState(true)
  const dateError = form.from && form.to && form.from > form.to ? t('The start date must be on or before the end date.') : undefined
  const filters: IncidentFilters = {
    electionId: form.electionId || undefined,
    stateId: form.stateId || undefined,
    lgaId: form.lgaId || undefined,
    wardId: form.wardId || undefined,
    category: (form.category || undefined) as IncidentCategory | undefined,
    severity: (form.severity || undefined) as IncidentSeverity | undefined,
    status: (form.status || undefined) as IncidentStatus | undefined,
    occurredFrom: dateError ? undefined : startOfDay(form.from),
    occurredTo: dateError ? undefined : endOfDay(form.to),
  }
  const stats = useIncidentStats(filters)
  const set = (patch: Partial<typeof EMPTY_FILTERS>) => setForm((current) => ({ ...current, ...patch }))
  const filterKey = JSON.stringify(filters)

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Incidents')}
        description={t('Triage, review and publish public reports.')}
      />
      <Alert variant="warning">
        <ShieldAlertIcon />
        <AlertTitle>{t('Confidential review area')}</AlertTitle>
        <AlertDescription>{t(ALLEGATION_NOTICE)}</AlertDescription>
      </Alert>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t('Filters')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormField id="incident-filter-election" label={t('Election')}>
              <Select id="incident-filter-election" value={form.electionId} onChange={(e) => set({ electionId: e.target.value })}>
                <option value="">{t('All elections')}</option>
                {elections.data?.data.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="incident-filter-category" label={t('Category')}>
              <Select id="incident-filter-category" value={form.category} onChange={(e) => set({ category: e.target.value })}>
                <option value="">{t('All categories')}</option>
                {(Object.keys(INCIDENT_CATEGORIES) as IncidentCategory[]).map((key) => (
                  <option key={key} value={key}>
                    {t(INCIDENT_CATEGORIES[key])}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="incident-filter-severity" label={t('Severity')}>
              <Select id="incident-filter-severity" value={form.severity} onChange={(e) => set({ severity: e.target.value })}>
                <option value="">{t('All severities')}</option>
                {(Object.keys(INCIDENT_SEVERITIES) as IncidentSeverity[]).map((key) => (
                  <option key={key} value={key}>
                    {t(INCIDENT_SEVERITIES[key])}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="incident-filter-status" label={t('Status')}>
              <Select id="incident-filter-status" value={form.status} onChange={(e) => set({ status: e.target.value })}>
                <option value="">{t('All statuses')}</option>
                {(Object.keys(INCIDENT_STATUSES) as IncidentStatus[]).map((key) => (
                  <option key={key} value={key}>
                    {t(INCIDENT_STATUSES[key])}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          <LocationSelect
            idPrefix="incident-filter-location"
            value={{ stateId: form.stateId || undefined, lgaId: form.lgaId || undefined, wardId: form.wardId || undefined }}
            onChange={(next) => set({ stateId: next.stateId ?? '', lgaId: next.lgaId ?? '', wardId: next.wardId ?? '' })}
          />
          <div className="grid items-end gap-4 sm:grid-cols-3">
            <FormField id="incident-filter-from" label={t('Occurred from')} error={dateError}>
              <Input
                id="incident-filter-from"
                type="date"
                value={form.from}
                aria-invalid={Boolean(dateError)}
                aria-describedby={describedBy('incident-filter-from', dateError)}
                onChange={(e) => set({ from: e.target.value })}
              />
            </FormField>
            <FormField id="incident-filter-to" label={t('Occurred to')}>
              <Input id="incident-filter-to" type="date" value={form.to} onChange={(e) => set({ to: e.target.value })} />
            </FormField>
            <div>
              <Button variant="outline" onClick={() => setForm(EMPTY_FILTERS)} disabled={JSON.stringify(form) === JSON.stringify(EMPTY_FILTERS)}>
                <RotateCcwIcon />
                {t('Clear filters')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {stats.isPending ? (
        <LoadingState variant="skeleton" rows={2} label={t('Loading totals')} />
      ) : stats.isError ? (
        <ErrorState message={errorMessage(stats.error, t('Totals could not be loaded.'))} onRetry={() => void stats.refetch()} />
      ) : (
        <>
          <section aria-label={t('Totals')} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard title={t('Total reports')} value={stats.data.total} detail={t('Matching the filters.')} />
            <StatCard
              title={t('Awaiting review')}
              value={stats.data.awaiting_review}
              detail={t('Received or in screening.')}
              tone={stats.data.awaiting_review ? 'text-info' : undefined}
            />
            <StatCard
              title={t('Under investigation')}
              value={stats.data.under_investigation}
              detail={t('Under review or awaiting corroboration.')}
            />
            <StatCard
              title={t('Verified')}
              value={stats.data.verified}
              detail={t('Confirmed by reviewers against evidence.')}
              tone="text-success"
            />
            <StatCard title={t('Unverified')} value={stats.data.unverified} detail={t('Reviewed, but could not be supported.')} />
            <StatCard title={t('Inconclusive')} value={stats.data.inconclusive} detail={t('Neither confirmed nor ruled out.')} />
            <StatCard
              title={t('Possible duplicates')}
              value={stats.data.possible_duplicates}
              detail={t('Closely matching an earlier report.')}
              tone={stats.data.possible_duplicates ? 'text-warning' : undefined}
            />
            <StatCard
              title={t('Critical and open')}
              value={stats.data.critical_open}
              detail={t('Possible loss of life or grave harm.')}
              tone={stats.data.critical_open ? 'text-destructive' : undefined}
            />
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Bars title={t('By category')} items={stats.data.by_category} empty={t('No reports yet.')} />
            <Bars title={t('By public stage')} items={stats.data.by_band} empty={t('No reports yet.')} />
            <Bars
              title={t('By state')}
              items={stats.data.by_state.map((area): CountItem => ({ key: area.id, label: area.name, count: area.count }))}
              empty={t('No reports yet.')}
            />
            <Bars
              title={t('By LGA (top 10)')}
              items={stats.data.by_lga
                .slice(0, 10)
                .map((area): CountItem => ({ key: area.id, label: area.parent ? `${area.name}, ${area.parent}` : area.name, count: area.count }))}
              empty={t('No reports yet.')}
            />
          </div>
          <Timeline points={stats.data.timeline} bucket={stats.data.timeline_bucket} />
        </>
      )}

      <section className="space-y-3" aria-labelledby="incident-list-heading">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="incident-list-heading" className="text-lg font-semibold">
            {queue ? t('Review queue') : t('All reports')}
          </h2>
          <div className="flex gap-1" role="group" aria-label={t('List view')}>
            <Button size="sm" variant={queue ? 'default' : 'outline'} aria-pressed={queue} onClick={() => setQueue(true)}>
              <ListChecksIcon />
              {t('Review queue')}
            </Button>
            <Button size="sm" variant={queue ? 'outline' : 'default'} aria-pressed={!queue} onClick={() => setQueue(false)}>
              {t('All reports')}
            </Button>
          </div>
        </div>
        <IncidentListing key={`${filterKey}-${queue}`} filters={filters} queue={queue} />
      </section>
    </div>
  )
}

function AttachmentImage({ incidentId, attachment }: { incidentId: string; attachment: IncidentAttachment }) {
  const t = useT()
  const image = useIncidentAttachment(incidentId, attachment.id)
  if (image.isPending) return <LoadingState label={t('Loading photo')} />
  if (image.isError) return <p className="text-sm text-destructive">{errorMessage(image.error, t('The photo could not be loaded.'))}</p>
  return (
    <figure className="space-y-2">
      <img src={image.data.url} alt={t('Photo attached to the report')} className="max-h-96 w-full rounded-lg border object-contain" />
      <figcaption className="break-all text-xs text-muted-foreground">
        {attachment.width}×{attachment.height} · SHA-256 {attachment.sha256}
        {image.data.sha256 && image.data.sha256 !== attachment.sha256 && (
          <span className="block font-medium text-destructive">{t('Fingerprint mismatch. Do not rely on this photo.')}</span>
        )}
      </figcaption>
    </figure>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  )
}

function TriagePanel({ detail }: { detail: IncidentDetail }) {
  const t = useT()
  const triage = detail.triage
  const suggestion = triage.classification?.suggested_category
  const keywords = Object.entries(triage.classification?.matched_keywords ?? {})
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('Automatic triage')}</CardTitle>
        <CardDescription>
          {t('Fixed keyword and similarity rules. Suggestions only: they never change the report or its status.')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <p className="font-medium">{t('Severity')}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
            {(triage.severity?.reasons ?? []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">{t('Category suggestion')}</p>
          <p className="text-muted-foreground">
            {suggestion
              ? triage.classification?.agrees_with_reporter
                ? t('Agrees with the reporter: {category}.', { category: t(INCIDENT_CATEGORIES[suggestion]) })
                : t('Keywords suggest {category}. The reporter chose {reported}.', {
                    category: t(INCIDENT_CATEGORIES[suggestion]),
                    reported: t(INCIDENT_CATEGORIES[detail.reported_category]),
                  })
              : t('No clear keyword match.')}
          </p>
          {keywords.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {keywords
                .map(([category, words]) => `${t(INCIDENT_CATEGORIES[category as IncidentCategory] ?? category)}: ${words.join(', ')}`)
                .join(' · ')}
            </p>
          )}
        </div>
        {(triage.missing_information ?? []).length > 0 && (
          <div>
            <p className="font-medium">{t('Missing information')}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">
              {triage.missing_information!.map((item) => (
                <li key={item.field}>{item.message}</li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <p className="font-medium">{t('Similar reports nearby')}</p>
          {(triage.similar_reports ?? []).length === 0 ? (
            <p className="text-muted-foreground">{t('None found in the same LGA, category and time window.')}</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {triage.similar_reports!.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center gap-2">
                  <Link to={`/admin/incidents/${item.id}`} className="font-mono text-xs text-primary hover:underline">
                    {item.reference}
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    {t('{pct}% word overlap', { pct: Math.round(item.similarity * 100) })}
                    {item.same_polling_unit ? ` · ${t('same polling unit')}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {detail.possible_duplicate_of && (
            <p className="mt-1 text-xs text-warning">
              {t('Possible duplicate of {reference}. Check before treating it as independent corroboration.', {
                reference: detail.possible_duplicate_of,
              })}
            </p>
          )}
        </div>
        {triage.personal_data_redacted && (
          <p className="text-xs text-muted-foreground">{t('Phone numbers or e-mail addresses were masked in the description.')}</p>
        )}
      </CardContent>
    </Card>
  )
}

function ReviewForm({ detail }: { detail: IncidentDetail }) {
  const t = useT()
  const review = useReviewIncident(detail.id)
  const [status, setStatus] = useState<IncidentStatus | ''>('')
  const [reason, setReason] = useState('')
  const [refs, setRefs] = useState('')
  const [category, setCategory] = useState<IncidentCategory | ''>('')
  const [severity, setSeverity] = useState<IncidentSeverity | ''>('')
  const [publish, setPublish] = useState(detail.is_public)
  const [summary, setSummary] = useState(detail.public_summary ?? '')
  const [error, setError] = useState<string>()

  const target = status || detail.status
  const publishable = target === 'verified' || (target === 'resolved' && (detail.status === 'verified' || detail.resolution_basis === 'verified'))
  const evidenceRefs = refs
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    if (!status) return setError(t('Choose the new status.'))
    if (reason.trim().length < 10) return setError(t('Give a reason of at least 10 characters.'))
    if (status === 'verified' && detail.status !== 'verified' && evidenceRefs.length === 0) return setError(t('Verification needs at least one evidence reference.'))
    if (publish && publishable && summary.trim().length < 20) return setError(t('Write a public summary of at least 20 characters.'))
    try {
      await review.mutateAsync({
        new_status: status,
        reason: reason.trim(),
        evidence_refs: evidenceRefs,
        category: category || undefined,
        severity: severity || undefined,
        publish: publishable ? publish : undefined,
        public_summary: publishable && publish ? summary.trim() : undefined,
      })
      setStatus('')
      setReason('')
      setRefs('')
      setCategory('')
      setSeverity('')
    } catch (caught) {
      setError(errorMessage(caught, t('The review could not be saved.')))
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate aria-label={t('Review this report')}>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField id="review-status" label={t('New status')} required>
          <Select id="review-status" value={status} onChange={(e) => setStatus(e.target.value as IncidentStatus | '')}>
            <option value="">{t('Choose')}</option>
            <option value={detail.status}>{t('Keep as {status}', { status: t(INCIDENT_STATUSES[detail.status]) })}</option>
            {detail.allowed_transitions.map((value) => (
              <option key={value} value={value}>
                {t(INCIDENT_STATUSES[value])}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="review-category" label={t('Correct category')}>
          <Select id="review-category" value={category} onChange={(e) => setCategory(e.target.value as IncidentCategory | '')}>
            <option value="">{t('Keep {category}', { category: t(INCIDENT_CATEGORIES[detail.category]) })}</option>
            {(Object.keys(INCIDENT_CATEGORIES) as IncidentCategory[])
              .filter((key) => key !== detail.category)
              .map((key) => (
                <option key={key} value={key}>
                  {t(INCIDENT_CATEGORIES[key])}
                </option>
              ))}
          </Select>
        </FormField>
        <FormField id="review-severity" label={t('Correct severity')}>
          <Select id="review-severity" value={severity} onChange={(e) => setSeverity(e.target.value as IncidentSeverity | '')}>
            <option value="">{t('Keep {severity}', { severity: t(INCIDENT_SEVERITIES[detail.severity]) })}</option>
            {(Object.keys(INCIDENT_SEVERITIES) as IncidentSeverity[])
              .filter((key) => key !== detail.severity)
              .map((key) => (
                <option key={key} value={key}>
                  {t(INCIDENT_SEVERITIES[key])}
                </option>
              ))}
          </Select>
        </FormField>
      </div>
      <FormField id="review-reason" label={t('Reason')} required hint={t('Recorded in the review history and audit trail.')}>
        <Textarea id="review-reason" rows={3} maxLength={2000} value={reason} aria-describedby="review-reason-hint" onChange={(e) => setReason(e.target.value)} />
      </FormField>
      <FormField
        id="review-refs"
        label={status === 'verified' ? t('Evidence references (required)') : t('Evidence references')}
        hint={t('One per line, for example evidence:SUBMISSION-ID or update:REFERENCE.')}
      >
        <Textarea id="review-refs" rows={2} value={refs} aria-describedby="review-refs-hint" onChange={(e) => setRefs(e.target.value)} />
      </FormField>
      {publishable ? (
        <div className="space-y-3 rounded-lg border p-3">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="size-4 accent-primary" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
            {t('Publish a public summary')}
          </label>
          {publish && (
            <FormField
              id="review-summary"
              label={t('Public summary')}
              required
              hint={t('Shown publicly. Describe what was verified without naming individuals, parties or reporters.')}
            >
              <Textarea id="review-summary" rows={3} maxLength={500} value={summary} aria-describedby="review-summary-hint" onChange={(e) => setSummary(e.target.value)} />
            </FormField>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {detail.is_public
            ? t('Moving away from Verified removes the public summary.')
            : t('Only verified reports can have a public summary.')}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={review.isPending}>
        {review.isPending && <Spinner />}
        {t('Save review')}
      </Button>
    </form>
  )
}

const REPORTER_LABEL = {
  anonymous: 'Anonymous. No account attached.',
  protected: 'Protected. The account is hidden from reviewers.',
  account: 'Signed-in account',
} as const

export function IncidentDetailPage() {
  const t = useT()
  const { incidentId = '' } = useParams()
  const incident = useIncident(incidentId)
  const [copied, setCopied] = useState(false)

  const back = (
    <Button asChild variant="ghost" size="sm">
      <Link to="/admin/incidents">
        <ArrowLeftIcon />
        {t('Incident reports')}
      </Link>
    </Button>
  )
  if (incident.isPending) return <LoadingState label={t('Loading report')} />
  if (incident.isError) {
    return (
      <div className="space-y-4">
        {back}
        <ErrorState message={errorMessage(incident.error, t('The report could not be loaded.'))} onRetry={() => void incident.refetch()} />
      </div>
    )
  }
  const detail = incident.data

  return (
    <div className="space-y-6">
      {back}
      <PageHeader
        eyebrow={t(INCIDENT_CATEGORIES[detail.category])}
        title={detail.reference}
        description={t('Received {time} via {channel}.', { time: when(detail.received_at), channel: detail.channel })}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              void navigator.clipboard
                ?.writeText(detail.reference)
                .then(() => setCopied(true))
                .catch(() => undefined)
            }
          >
            <CopyIcon />
            {copied ? t('Copied') : t('Copy reference')}
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        <StatusBadge status={detail.status} />
        <SeverityBadge severity={detail.severity} />
        <span className="text-xs text-muted-foreground">{t('Public stage:')}</span>
        <BandBadge band={detail.band} />
        {detail.is_public && <Badge variant="success">{t('Published')}</Badge>}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('Original report')}</CardTitle>
              <CardDescription>{t('As submitted, after masking of phone numbers and e-mails. Never edited by reviewers.')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-wrap text-sm">{detail.description}</p>
              <dl className="grid gap-3 sm:grid-cols-2">
                <Field label={t('Category chosen by reporter')}>{t(INCIDENT_CATEGORIES[detail.reported_category])}</Field>
                <Field label={t('Current category')}>{t(INCIDENT_CATEGORIES[detail.category])}</Field>
                <Field label={t('Location')}>
                  <span className="flex items-start gap-1">
                    <MapPinIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    <span>
                      {[detail.polling_unit && `${detail.polling_unit.code ?? ''} ${detail.polling_unit.name}`.trim(), detail.ward?.name, detail.lga.name, detail.state.name]
                        .filter(Boolean)
                        .join(', ')}
                    </span>
                  </span>
                </Field>
                <Field label={t('When it happened')}>
                  {when(detail.occurred_at, detail.time_is_approximate)}
                  {detail.time_is_approximate && <span className="text-xs text-muted-foreground"> ({t('approximate')})</span>}
                </Field>
                <Field label={t('Map location')}>
                  {detail.latitude !== null && detail.longitude !== null ? (
                    <a
                      className="text-primary hover:underline"
                      href={`https://www.openstreetmap.org/?mlat=${detail.latitude}&mlon=${detail.longitude}#map=16/${detail.latitude}/${detail.longitude}`}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {detail.latitude.toFixed(4)}, {detail.longitude.toFixed(4)}
                    </a>
                  ) : (
                    t('Not shared')
                  )}
                </Field>
                <Field label={t('Reporter')}>
                  {t(REPORTER_LABEL[detail.reporter])}
                  {detail.reporter_user_id && <span className="block font-mono text-xs text-muted-foreground">{detail.reporter_user_id}</span>}
                </Field>
              </dl>
            </CardContent>
          </Card>

          {detail.attachments.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('Photo')}</CardTitle>
                <CardDescription>{t('Private. Location and camera details were removed when it was received.')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {detail.attachments.map((attachment) => (
                  <AttachmentImage key={attachment.id} incidentId={detail.id} attachment={attachment} />
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('Review history')}</CardTitle>
            </CardHeader>
            <CardContent>
              {detail.reviews.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('Not reviewed yet.')}</p>
              ) : (
                <ol className="space-y-4">
                  {detail.reviews.map((item) => (
                    <li key={item.id} className="border-l-2 pl-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={item.previous_status} />
                        <span aria-hidden>→</span>
                        <span className="sr-only">{t('to')}</span>
                        <StatusBadge status={item.new_status} />
                        <span className="text-xs text-muted-foreground">{when(item.created_at)}</span>
                      </div>
                      <p className="mt-1">{item.reason}</p>
                      <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                        {t('Reviewer')} {item.reviewer_id}
                      </p>
                      {item.category_to && (
                        <p className="text-xs text-muted-foreground">
                          {t('Category')}: {t(INCIDENT_CATEGORIES[item.category_from ?? item.category_to])} → {t(INCIDENT_CATEGORIES[item.category_to])}
                        </p>
                      )}
                      {item.severity_to && (
                        <p className="text-xs text-muted-foreground">
                          {t('Severity')}: {t(INCIDENT_SEVERITIES[item.severity_from ?? item.severity_to])} → {t(INCIDENT_SEVERITIES[item.severity_to])}
                        </p>
                      )}
                      {item.evidence_refs.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          {t('Evidence')}: {item.evidence_refs.join(', ')}
                        </p>
                      )}
                      {item.public_summary && (
                        <p className="mt-1 text-xs">
                          {item.published ? t('Published:') : t('Unpublished:')} {item.public_summary}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('Review')}</CardTitle>
              {!detail.can_review && (
                <CardDescription>
                  {t('Read only. Reviewing needs a reviewer role, and nobody can review a report they submitted.')}
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>{detail.can_review && <ReviewForm key={detail.status_changed_at} detail={detail} />}</CardContent>
          </Card>
          {detail.is_public && detail.public_summary && (
            <Alert variant="success">
              <AlertTitle>{t('Public summary')}</AlertTitle>
              <AlertDescription>{detail.public_summary}</AlertDescription>
            </Alert>
          )}
          <TriagePanel detail={detail} />
        </div>
      </div>
    </div>
  )
}
