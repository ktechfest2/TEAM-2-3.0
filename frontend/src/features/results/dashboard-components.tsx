import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ClipboardListIcon,
  DatabaseIcon,
  FileWarningIcon,
  HistoryIcon,
  InfoIcon,
  MapPinOffIcon,
  RadioIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/features/directory/data-notice'
import type { LiveStatus } from '@/features/results/api'
import {
  DEMO_RESULT_LABEL,
  LEVEL_LABEL,
  SERIES_COLOURS,
  UNIT_STATUS_META,
  formatCount,
  formatPct,
  resultsPath,
  useResultsBase,
} from '@/features/results/format'
import type {
  AlertSummary,
  AreaSummary,
  Coverage,
  DataStatus,
  ElectionRef,
  Level,
  PartyResultsResponse,
  ProgressResponse,
  UnitResultStatus,
} from '@/features/results/types'
import type { CachedResult } from '@/lib/offline/public-cache'

type Origin = Pick<CachedResult<unknown>, 'origin' | 'syncedAt'>

export function DemoResultBanner({ label }: { label?: string | null }) {
  return (
    <p role="note" className="text-sm font-medium text-warning">
      {label ?? DEMO_RESULT_LABEL}
    </p>
  )
}

export function CivicNotice({ notice, partial }: { notice: string; partial?: string }) {
  return (
    <div className="space-y-1 text-sm text-muted-foreground">
      <p>{notice}</p>
      {partial && <p>{partial}</p>}
    </div>
  )
}

export function CachedDataNotice({ result }: { result: Origin }) {
  if (result.origin !== 'cache') return null
  return (
    <Alert variant="warning">
      <HistoryIcon />
      <AlertTitle>Saved copy. This is not live data</AlertTitle>
      <AlertDescription>
        These figures were saved on this device at {formatDateTime(result.syncedAt)}. They will not change until you
        reconnect, and newer submissions may exist.
      </AlertDescription>
    </Alert>
  )
}

const LIVE_META: Record<LiveStatus, { label: string; variant: 'success' | 'neutral' | 'warning' }> = {
  live: { label: 'Live updates on', variant: 'success' },
  connecting: { label: 'Connecting to live updates', variant: 'neutral' },
  reconnecting: { label: 'Live updates interrupted, retrying', variant: 'warning' },
  unavailable: { label: 'Live updates unavailable, refreshing periodically', variant: 'neutral' },
}

export function dataStatusLabel(status: DataStatus, origin: Origin['origin']) {
  if (origin === 'cache') return 'Saved on this device (not live)'
  return status === 'demonstration' ? 'Demonstration data from the server' : 'Current server data'
}

type FreshnessProps = {
  election: ElectionRef
  level: Level
  areaName: string
  coverage: Coverage
  dataStatus: DataStatus
  generatedAt: string
  lastUpdatedAt: string | null
  result: Origin
  live: LiveStatus
  sourceRecordsHref: string
}

/** Answers "how fresh is this, where did it come from, and how complete is it?" in one place. */
export function FreshnessPanel(props: FreshnessProps) {
  const { election, level, areaName, coverage, dataStatus, generatedAt, lastUpdatedAt, result, live } = props
  const liveMeta = result.origin === 'cache' ? LIVE_META.unavailable : LIVE_META[live]
  const rows: [string, ReactNode][] = [
    ['Last result change', formatDateTime(lastUpdatedAt)],
    ['Figures generated', formatDateTime(generatedAt)],
    [result.origin === 'cache' ? 'Saved on device' : 'Fetched', formatDateTime(result.syncedAt)],
    ['Election', `${election.name} (ID ${election.id})`],
    ['Aggregation level', `${LEVEL_LABEL[level]}, ${areaName}`],
    ['Data status', dataStatusLabel(dataStatus, result.origin)],
  ]
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <DatabaseIcon className="size-4" aria-hidden /> Freshness and provenance
        </CardTitle>
        <Badge variant={liveMeta.variant} aria-live="polite">
          <RadioIcon aria-hidden /> {liveMeta.label}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {rows.map(([term, value]) => (
            <div key={term} className="min-w-0">
              <dt className="text-xs text-muted-foreground">{term}</dt>
              <dd className="font-medium break-words">{value}</dd>
            </div>
          ))}
        </dl>
        <Link to={props.sourceRecordsHref} className="inline-flex text-sm font-medium text-navy hover:underline">
          View the {formatCount(coverage.polling_units_with_submissions)} polling units with submissions
        </Link>
      </CardContent>
    </Card>
  )
}

export function CoverageBar({ coverage, label }: { coverage: Coverage; label?: string }) {
  const expected = Math.max(coverage.expected_polling_units, 1)
  const verified = (coverage.verified_polling_units / expected) * 100
  const reportingOnly = ((coverage.reporting_polling_units - coverage.verified_polling_units) / expected) * 100
  return (
    <div className="space-y-1.5">
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={label ?? `${coverage.reporting_label}. ${coverage.verification_label}.`}
      >
        <span className="bg-success" style={{ width: `${verified}%` }} />
        <span className="bg-info/60" style={{ width: `${reportingOnly}%` }} />
      </div>
    </div>
  )
}

export function CoverageLegend() {
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full bg-success" aria-hidden /> Verified
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full bg-info/60" aria-hidden /> Reporting, not yet verified
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full bg-muted ring-1 ring-border" aria-hidden /> No reportable result
      </span>
    </p>
  )
}

export function OverviewCards({ coverage }: { coverage: Coverage }) {
  const figures: [string, string][] = [
    ['Expected polling units', formatCount(coverage.expected_polling_units)],
    ['Unique polling units reporting', formatCount(coverage.reporting_polling_units)],
    ['Verified polling units', formatCount(coverage.verified_polling_units)],
    ['Submissions received', formatCount(coverage.submission_count)],
  ]
  return (
    <section aria-labelledby="overview-heading" className="space-y-4">
      <h2 id="overview-heading" className="sr-only">
        Coverage overview
      </h2>
      <div>
        <p className="text-lg font-semibold tracking-tight">{coverage.reporting_label}</p>
        <p className="mt-1 text-sm text-muted-foreground">{coverage.verification_label}</p>
      </div>
      <CoverageBar coverage={coverage} />
      <CoverageLegend />
      <dl className="grid grid-cols-2 border-y sm:grid-cols-4">
        {figures.map(([label, value]) => (
          <div key={label} className="border-b px-4 py-3 sm:border-b-0 sm:border-r sm:last:border-r-0">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-muted-foreground">
        {formatCount(coverage.pending_polling_units)} pending verification
        {' · '}
        {formatCount(coverage.flagged_polling_units)} flagged for review
        {' · '}
        {formatCount(coverage.conflict_polling_units)} conflicting
        {' · '}
        {formatCount(coverage.rejected_submission_count)} rejected
      </p>
    </section>
  )
}

function shareText(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${value.toFixed(1)}%`
}

function shareWidth(value: number | null | undefined) {
  return `${Math.min(Math.max(value ?? 0, 0), 100)}%`
}

/** Two tracks, in the same colours as the coverage bar: reported, then verified. */
function ShareBars({ reported, verified }: { reported: number | null | undefined; verified: number | null | undefined }) {
  const tracks = [
    ['bg-info/70', shareWidth(reported)],
    ['bg-success', shareWidth(verified)],
  ] as const
  return (
    <span className="mt-2 flex max-w-xs flex-col gap-1" aria-hidden>
      {tracks.map(([colour, width]) => (
        <span key={colour} className="block h-1 overflow-hidden rounded-full bg-muted">
          <span className={`block h-full rounded-full ${colour}`} style={{ width }} />
        </span>
      ))}
    </span>
  )
}

/** Reported and verified figures side by side, in ballot order, with no ranking or winner language. */
export function PartyResultsPanel({ data }: { data: Pick<PartyResultsResponse, 'reported' | 'verified'> }) {
  const { reported, verified } = data
  const verifiedByCode = new Map(verified.parties.map((p) => [p.code, p]))
  const totals: [string, number, number][] = [
    ['Valid votes', reported.total_valid_votes, verified.total_valid_votes],
    ['Rejected', reported.rejected_votes, verified.rejected_votes],
    ['Votes cast', reported.total_votes_cast, verified.total_votes_cast],
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Party results</CardTitle>
        <CardDescription>In ballot order. The percentage is each party&apos;s share of party votes.</CardDescription>
      </CardHeader>
      <CardContent className="px-0 pb-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Reported and verified votes per party</caption>
            <colgroup>
              <col />
              <col className="w-28" />
              <col className="w-28" />
            </colgroup>
            <thead>
              <tr className="border-y bg-muted/40 text-xs text-muted-foreground">
                <th scope="col" className="px-5 py-2 text-left font-medium">
                  Party
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Reported
                  <span className="mt-0.5 block font-normal whitespace-nowrap tabular-nums">
                    {formatCount(reported.polling_units_included)} / {formatCount(reported.expected_polling_units)}
                  </span>
                </th>
                <th scope="col" className="py-2 pr-5 pl-3 text-right font-medium">
                  Verified
                  <span className="mt-0.5 block font-normal whitespace-nowrap tabular-nums">
                    {formatCount(verified.polling_units_included)} / {formatCount(verified.expected_polling_units)}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {reported.parties.map((party) => {
                const matched = verifiedByCode.get(party.code)
                return (
                  <tr key={party.code} className="border-b">
                    <th scope="row" className="px-5 py-3 text-left font-medium">
                      <span className="mr-2 font-semibold text-navy">{party.code}</span>
                      <span className="font-normal text-muted-foreground">{party.name}</span>
                      <ShareBars reported={party.share_pct} verified={matched?.share_pct} />
                    </th>
                    <td className="px-3 py-3 text-right align-top">
                      <span className="block font-semibold tabular-nums">{formatCount(party.votes)}</span>
                      <span className="block text-xs text-muted-foreground tabular-nums">{shareText(party.share_pct)}</span>
                    </td>
                    <td className="py-3 pr-5 pl-3 text-right align-top">
                      <span className="block font-semibold tabular-nums">{formatCount(matched?.votes ?? 0)}</span>
                      <span className="block text-xs text-muted-foreground tabular-nums">{shareText(matched?.share_pct)}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="text-xs">
              {totals.map(([label, reportedValue, verifiedValue], index) => {
                const last = index === totals.length - 1
                return (
                  <tr key={label} className={index === 0 ? 'border-t' : undefined}>
                    <th
                      scope="row"
                      className={`px-5 py-1.5 text-left ${last ? 'font-medium text-foreground' : 'font-normal text-muted-foreground'}`}
                    >
                      {label}
                    </th>
                    <td className={`px-3 py-1.5 text-right tabular-nums ${last ? 'font-medium' : 'text-muted-foreground'}`}>
                      {formatCount(reportedValue)}
                    </td>
                    <td className={`py-1.5 pr-5 pl-3 text-right tabular-nums ${last ? 'font-medium' : 'text-muted-foreground'}`}>
                      {formatCount(verifiedValue)}
                    </td>
                  </tr>
                )
              })}
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

export function UnitStatusBadge({ status }: { status: UnitResultStatus }) {
  const meta = UNIT_STATUS_META[status]
  return (
    <Badge variant={meta.variant} title={meta.description}>
      {meta.label}
    </Badge>
  )
}

type AreaTableProps = {
  title: string
  childLevel: Level
  items: AreaSummary[]
  electionId: string
  reporting: number
  outstanding: number
}

export function AreaProgressTable({ title, childLevel, items, electionId, reporting, outstanding }: AreaTableProps) {
  const { base } = useResultsBase()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}: reporting progress</CardTitle>
        <CardDescription>
          {formatCount(reporting)} reporting · {formatCount(outstanding)} with no reportable result yet
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th scope="col" className="py-2 pr-3 font-medium">
                {LEVEL_LABEL[childLevel]}
              </th>
              <th scope="col" className="w-1/3 py-2 pr-3 font-medium">
                Coverage
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">
                Reporting
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">
                Verified
              </th>
              <th scope="col" className="py-2 text-right font-medium">
                Needs attention
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((child) => {
              const c = child.coverage
              return (
                <tr key={child.area.id} className="border-b last:border-0">
                  <th scope="row" className="py-2 pr-3 text-left font-medium">
                    <Link
                      to={resultsPath(base, childLevel, child.area.id, electionId)}
                      className="text-navy hover:underline"
                    >
                      {child.area.name}
                    </Link>
                  </th>
                  <td className="py-2 pr-3">
                    <CoverageBar coverage={c} />
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {c.reporting_polling_units} / {c.expected_polling_units}{' '}
                    <span className="text-muted-foreground">({formatPct(c.reporting_coverage_pct)})</span>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {c.verified_polling_units} / {c.expected_polling_units}{' '}
                    <span className="text-muted-foreground">({formatPct(c.verification_coverage_pct)})</span>
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {c.flagged_polling_units ? <Badge variant="warning">{c.flagged_polling_units} flagged</Badge> : '-'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

/** Small multiples instead of a single chart so no area is visually "won" by a party. */
export function AreaComparisonChart({ data, title }: { data: PartyResultsResponse; title: string }) {
  const codes = data.reported.parties.map((p) => p.code)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="flex flex-wrap gap-3 text-xs" aria-label="Party colour key">
          {codes.map((code, i) => (
            <li key={code} className="inline-flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-sm"
                style={{ background: SERIES_COLOURS[i % SERIES_COLOURS.length] }}
                aria-hidden
              />
              {code}
            </li>
          ))}
        </ul>
        {data.breakdown.map((row) => {
          const total = row.reported.parties.reduce((sum, p) => sum + p.votes, 0)
          const description = row.reported.parties.map((p) => `${p.code} ${formatPct(p.share_pct)}`).join(', ')
          return (
            <div key={row.area.id} className="grid gap-1 text-xs sm:grid-cols-[10rem_1fr] sm:items-center sm:gap-3">
              <span className="font-medium">
                {row.area.name}
                <span className="block font-normal text-muted-foreground">
                  {row.reported.polling_units_included} of {row.reported.expected_polling_units} units reported
                </span>
              </span>
              {total ? (
                <div
                  className="flex h-4 overflow-hidden rounded-sm bg-muted"
                  role="img"
                  aria-label={`${row.area.name}: ${description} of reported party votes`}
                >
                  {row.reported.parties.map((p, i) => (
                    <span
                      key={p.code}
                      style={{
                        width: `${(p.votes / total) * 100}%`,
                        background: SERIES_COLOURS[i % SERIES_COLOURS.length],
                      }}
                    />
                  ))}
                </div>
              ) : (
                <span className="text-muted-foreground">No reported result yet</span>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

export function ProgressChart({ data }: { data: ProgressResponse }) {
  const points = data.points
  const width = 640
  const height = 200
  const pad = { left: 36, right: 12, top: 12, bottom: 28 }
  const max = Math.max(1, data.expected_polling_units)
  const x = (i: number) => pad.left + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (width - pad.left - pad.right))
  const y = (v: number) => height - pad.bottom - (v / max) * (height - pad.top - pad.bottom)
  const line = (key: 'reporting_polling_units' | 'verified_polling_units') =>
    points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' ')
  const last = points.at(-1)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Reporting progress</CardTitle>
      </CardHeader>
      <CardContent>
        {points.length === 0 ? (
          <p className="text-sm text-muted-foreground">No polling unit has reported yet.</p>
        ) : (
          <figure className="space-y-2">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="h-auto w-full"
              role="img"
              aria-label={`Cumulative polling units: ${last?.reporting_polling_units ?? 0} reporting and ${last?.verified_polling_units ?? 0} verified of ${data.expected_polling_units} expected.`}
            >
              {[0, 0.5, 1].map((f) => (
                <g key={f}>
                  <line
                    x1={pad.left}
                    x2={width - pad.right}
                    y1={y(max * f)}
                    y2={y(max * f)}
                    className="stroke-border"
                    strokeDasharray="3 3"
                  />
                  <text x={pad.left - 6} y={y(max * f) + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">
                    {Math.round(max * f)}
                  </text>
                </g>
              ))}
              <path d={line('reporting_polling_units')} fill="none" stroke="var(--info)" strokeWidth={2.5} />
              <path d={line('verified_polling_units')} fill="none" stroke="var(--success)" strokeWidth={2.5} />
              {points.map((p, i) => (
                <g key={p.at}>
                  <circle cx={x(i)} cy={y(p.reporting_polling_units)} r={3.5} fill="var(--info)" />
                  <circle cx={x(i)} cy={y(p.verified_polling_units)} r={3.5} fill="var(--success)" />
                </g>
              ))}
              {points.length > 0 && (
                <>
                  <text x={pad.left} y={height - 8} className="fill-muted-foreground text-[10px]">
                    {formatDateTime(points[0]?.at)}
                  </text>
                  <text x={width - pad.right} y={height - 8} textAnchor="end" className="fill-muted-foreground text-[10px]">
                    {formatDateTime(last?.at)}
                  </text>
                </>
              )}
            </svg>
            <figcaption className="flex gap-4 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-info" aria-hidden /> Reporting polling units
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-success" aria-hidden /> Verified polling units
              </span>
              <span>Top line = {data.expected_polling_units} expected</span>
            </figcaption>
          </figure>
        )}
      </CardContent>
    </Card>
  )
}

const ALERT_ICON: Record<AlertSummary['kind'], typeof InfoIcon> = {
  unresolved_discrepancies: AlertTriangleIcon,
  records_requiring_review: ClipboardListIcon,
  unusual_patterns: FileWarningIcon,
  incomplete: MapPinOffIcon,
}

export function AlertsPanel({ alerts, recordsHref }: { alerts: AlertSummary[]; recordsHref: (kind: string) => string }) {
  const active = alerts.filter((a) => a.count > 0)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Needs attention</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {active.length === 0 && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2Icon className="size-4 text-success" aria-hidden /> No open alerts for this area.
          </p>
        )}
        {active.map((alert) => {
          const Icon = ALERT_ICON[alert.kind]
          const kind = alert.href ? (new URLSearchParams(alert.href.split('?')[1]).get('kind') ?? '') : ''
          return (
            <Link
              key={alert.kind}
              to={recordsHref(kind)}
              className="flex items-start gap-3 rounded-md border p-3 transition-colors hover:bg-muted"
            >
              <Icon className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {alert.title} <Badge variant="warning">{alert.count}</Badge>
                </span>
                <span className="sr-only">{alert.description}</span>
              </span>
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}
