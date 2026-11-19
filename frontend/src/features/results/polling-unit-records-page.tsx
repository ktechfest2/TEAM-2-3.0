import { Link, useSearchParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { type AreaLevel, usePollingUnitRecords } from '@/features/results/api'
import { CachedDataNotice } from '@/features/results/dashboard-components'
import { UNIT_STATUS_META, resultsPath, useResultsBase, useSelectedElection } from '@/features/results/format'
import { PollingUnitTable } from '@/features/results/polling-unit-table'
import type { DiscrepancyKind, UnitResultStatus } from '@/features/results/types'

const KIND_TITLE: Record<DiscrepancyKind, string> = {
  conflict: 'Polling units with conflicting submissions',
  flagged: 'Polling units requiring review',
  anomaly: 'Polling units with open VoteTrace AI alerts',
  pending: 'Polling units pending verification',
  incomplete: 'Polling units with incomplete location records',
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function readScope(params: URLSearchParams): { level: AreaLevel; areaId?: string } {
  for (const level of ['ward', 'lga', 'state'] as const) {
    const value = params.get(`${level}_id`)
    if (value && UUID.test(value)) return { level, areaId: value }
  }
  return { level: 'national' }
}

function oneOf<T extends string>(value: string | null, allowed: readonly T[]) {
  return allowed.find((item) => item === value)
}

/** The polling units behind any total: the traceability view for dashboards and alerts. */
export function PollingUnitRecordsPage() {
  const [params, setParams] = useSearchParams()
  const { base } = useResultsBase()
  const elections = useSelectedElection()
  const electionId = elections.selected?.id
  const scope = readScope(params)
  const kind = oneOf(params.get('kind'), Object.keys(KIND_TITLE) as DiscrepancyKind[])
  const status = oneOf(params.get('status'), Object.keys(UNIT_STATUS_META) as UnitResultStatus[])
  const page = Math.min(Math.max(Number.parseInt(params.get('page') ?? '1', 10) || 1, 1), 10_000)
  const query = usePollingUnitRecords({ ...scope, kind, status, page }, electionId)

  const setParam = (key: string, value: string | undefined) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })

  if (elections.query.isPending) return <LoadingState label="Loading elections…" />
  if (!electionId) return <EmptyState title="No elections available" />

  const title = kind ? KIND_TITLE[kind] : 'Polling units behind these totals'
  const back = resultsPath(base, scope.level, scope.areaId, electionId)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Source records"
        title={title}
        description="One row per polling unit. Open one for its report."
        actions={
          <Button asChild variant="outline">
            <Link to={back}>Back to dashboard</Link>
          </Button>
        }
      />
      {!kind && (
        <label className="flex max-w-xs flex-col gap-1 text-xs font-medium text-muted-foreground">
          Status
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={status ?? ''}
            onChange={(event) => setParam('status', event.target.value || undefined)}
          >
            <option value="">All polling units</option>
            {(Object.keys(UNIT_STATUS_META) as UnitResultStatus[]).map((value) => (
              <option key={value} value={value}>
                {UNIT_STATUS_META[value].label}
              </option>
            ))}
          </select>
        </label>
      )}
      {query.isPending ? (
        <LoadingState variant="skeleton" rows={6} />
      ) : query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : (
        <>
          <CachedDataNotice result={query.data} />
          <Card>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {query.data.data.total} polling unit{query.data.data.total === 1 ? '' : 's'}
              </p>
              {query.data.data.items.length === 0 ? (
                <p className="text-sm text-muted-foreground">No polling units match.</p>
              ) : (
                <PollingUnitTable items={query.data.data.items} electionId={electionId} />
              )}
              {query.data.data.total_pages > 1 && (
                <div className="flex items-center justify-between gap-2 text-sm">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setParam('page', String(page - 1))}
                  >
                    Previous
                  </Button>
                  <span>
                    Page {query.data.data.page} of {query.data.data.total_pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= query.data.data.total_pages}
                    onClick={() => setParam('page', String(page + 1))}
                  >
                    Next
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
