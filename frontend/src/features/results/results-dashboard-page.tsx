import { ChevronRightIcon, MapIcon } from 'lucide-react'
import { lazy, Suspense, useCallback, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { Election } from '@/features/evidence/types'
import {
  type AreaLevel,
  useArea,
  useLiveAnalytics,
  usePartyResults,
  usePollingUnitRecords,
  useProgress,
} from '@/features/results/api'
import {
  AlertsPanel,
  AreaComparisonChart,
  AreaProgressTable,
  CachedDataNotice,
  OverviewCards,
  PartyResultsPanel,
  ProgressChart,
} from '@/features/results/dashboard-components'
import { formatDateTime } from '@/features/directory/data-notice'
import {
  CHILD_LABEL,
  LEVEL_LABEL,
  formatCount,
  resultsPath,
  useResultsBase,
  useSelectedElection,
} from '@/features/results/format'
import { PollingUnitTable } from '@/features/results/polling-unit-table'
import type { AreaRef, AreaSummary } from '@/features/results/types'
import { useT } from '@/i18n/locale-provider'

const NigeriaMap = lazy(() => import('@/features/results/nigeria-map'))

export function ElectionSelect({
  items,
  selected,
  onSelect,
}: {
  items: Election[]
  selected?: Election
  onSelect: (id: string) => void
}) {
  if (items.length < 2) return null
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
      Election
      <select
        className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"
        value={selected?.id ?? ''}
        onChange={(event) => onSelect(event.target.value)}
      >
        {items.map((election) => (
          <option key={election.id} value={election.id}>
            {election.name}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Breadcrumbs({ crumbs, electionId }: { crumbs: AreaRef[]; electionId: string }) {
  const { base } = useResultsBase()
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1
          return (
            <li key={`${crumb.level}-${crumb.id ?? 'ng'}`} className="flex items-center gap-1">
              {index > 0 && <ChevronRightIcon className="size-3.5" aria-hidden />}
              {last ? (
                <span aria-current="page" className="font-medium text-foreground">
                  {crumb.name}
                </span>
              ) : (
                <Link to={resultsPath(base, crumb.level, crumb.id, electionId)} className="hover:underline">
                  {crumb.name}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function StateMapCard({ states, electionId }: { states: AreaSummary[]; electionId: string }) {
  const t = useT()
  const navigate = useNavigate()
  const { base } = useResultsBase()
  const onSelect = useCallback(
    (stateId: string) => void navigate(resultsPath(base, 'state', stateId, electionId)),
    [base, electionId, navigate],
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MapIcon className="size-4" aria-hidden /> {t('Reporting coverage by state')}
        </CardTitle>
        <CardDescription>{t('Select a state.')}</CardDescription>
      </CardHeader>
      <CardContent>
        <Suspense fallback={<LoadingState label={t('Loading map…')} />}>
          <NigeriaMap states={states} onSelect={onSelect} />
        </Suspense>
      </CardContent>
    </Card>
  )
}

function WardUnits({ wardId, electionId }: { wardId: string; electionId: string }) {
  const t = useT()
  const records = usePollingUnitRecords({ level: 'ward', areaId: wardId, page: 1 }, electionId)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('Polling units in this ward')}</CardTitle>
        <CardDescription>{t('Open a polling unit for its public verification report.')}</CardDescription>
      </CardHeader>
      <CardContent>
        {records.isPending ? (
          <LoadingState variant="skeleton" />
        ) : records.isError ? (
          <ErrorState onRetry={() => void records.refetch()} />
        ) : (
          <PollingUnitTable items={records.data.data.items} electionId={electionId} />
        )}
      </CardContent>
    </Card>
  )
}

/** One dashboard for every area level; the API decides what the area contains. */
export function ResultsDashboardPage({ level }: { level: AreaLevel }) {
  const t = useT()
  const { id } = useParams()
  const { base, staff } = useResultsBase()
  const elections = useSelectedElection()
  const electionId = elections.selected?.id
  const areaQuery = useArea(level, id, electionId)
  const parties = usePartyResults(level, id, electionId)
  const progress = useProgress(level, id, electionId)
  const live = useLiveAnalytics(electionId)
  const liveLabel = {
    live: t('Live updates on'),
    connecting: t('Connecting to live updates'),
    reconnecting: t('Live updates interrupted, retrying'),
    unavailable: t('Live updates unavailable, refreshing periodically'),
  }[live]
  const levelLabel = t(LEVEL_LABEL[level])
  const nationalTitle = staff ? t('Results') : t('National results dashboard')

  const shell = (body: ReactNode) => (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t('{level} level', { level: levelLabel })}
        title={level === 'national' ? nationalTitle : t('{level} results', { level: levelLabel })}
      />
      {body}
    </div>
  )
  if (elections.query.isPending) return shell(<LoadingState label={t('Loading elections…')} />)
  if (elections.query.isError)
    return shell(
      <ErrorState
        title={t('Results could not be loaded')}
        message={t('The results service is unreachable and no copy is saved on this device.')}
        onRetry={() => void elections.query.refetch()}
      />,
    )
  if (!electionId)
    return shell(
      <EmptyState title={t('No elections available')} description={t('Results appear once an election is set up.')} />,
    )
  if (areaQuery.isPending) return shell(<LoadingState variant="skeleton" rows={6} label={t('Loading results…')} />)
  if (areaQuery.isError)
    return shell(
      <ErrorState
        title={t('Results could not be loaded')}
        message={t('This area may not exist for the selected election, or the service is unreachable.')}
        onRetry={() => void areaQuery.refetch()}
      />,
    )

  const result = areaQuery.data
  const data = result.data
  const summary = data.summary
  const recordsHref = (kind?: string) => {
    const params = new URLSearchParams({ election: electionId })
    if (level !== 'national' && id) params.set(`${level}_id`, id)
    if (kind) params.set('kind', kind)
    return `${base}/records?${params.toString()}`
  }
  const title = level === 'national' ? nationalTitle : summary.area.name

  return (
    <div className="space-y-6">
      {level !== 'national' && <Breadcrumbs crumbs={data.breadcrumbs} electionId={electionId} />}
      <PageHeader
        eyebrow={t('{level} level · {name}', { level: levelLabel, name: data.election.name })}
        title={title}
        actions={<ElectionSelect items={elections.items} selected={elections.selected} onSelect={elections.select} />}
      />
      <CachedDataNotice result={result} />

      <OverviewCards coverage={summary.coverage} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <PartyResultsPanel data={data} />
        <AlertsPanel alerts={data.alerts} recordsHref={recordsHref} />
      </div>

      {level === 'national' && <StateMapCard states={data.children} electionId={electionId} />}

      {data.child_level && data.child_level !== 'polling_unit' && (
        <AreaProgressTable
          title={t(CHILD_LABEL[level])}
          childLevel={data.child_level}
          items={data.children}
          electionId={electionId}
          reporting={data.child_areas_reporting}
          outstanding={data.child_areas_outstanding}
        />
      )}
      {level === 'ward' && id && <WardUnits wardId={id} electionId={electionId} />}

      <div className="grid gap-6 lg:grid-cols-2">
        {parties.data && parties.data.data.breakdown.length > 0 && (
          <AreaComparisonChart data={parties.data.data} title={t('{label} compared', { label: t(CHILD_LABEL[level]) })} />
        )}
        {progress.data && <ProgressChart data={progress.data.data} />}
      </div>

      {result.origin !== 'cache' && (
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            {liveLabel}.{' '}
            {t('Last result change')} {formatDateTime(summary.last_updated_at)}
          </span>
          <Link to={recordsHref()} className="font-medium text-navy hover:underline">
            {t('View the {count} polling units with submissions', {
              count: formatCount(summary.coverage.polling_units_with_submissions),
            })}
          </Link>
        </p>
      )}
    </div>
  )
}
