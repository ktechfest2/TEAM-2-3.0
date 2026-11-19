import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { env } from '@/config/env'
import { buildPath } from '@/features/directory/api'
import type {
  AreaListResponse,
  AreaResponse,
  DiscrepancyKind,
  Level,
  PartyResultsResponse,
  PollingUnitPage,
  PollingUnitResultResponse,
  ProgressResponse,
  UnitResultStatus,
} from '@/features/results/types'
import { fetchPublic, type Timestamped } from '@/lib/offline/public-cache'

export const ANALYTICS_KEY = 'analytics'
/** Fallback refresh when live updates are unavailable (several API workers, proxies). */
const BACKGROUND_REFRESH_MS = 90_000
/** Batches bursts of changes so one dashboard stays well inside the API's per-client rate limit. */
const LIVE_DEBOUNCE_MS = 3_000

function useAnalyticsQuery<T extends Timestamped>(path: string, enabled = true) {
  return useQuery({
    queryKey: [ANALYTICS_KEY, path],
    queryFn: () => fetchPublic<T>(`/analytics${path}`),
    enabled,
    staleTime: 15_000,
    refetchInterval: BACKGROUND_REFRESH_MS,
    placeholderData: keepPreviousData,
  })
}

export type AreaLevel = Exclude<Level, 'polling_unit'>

const AREA_PATH: Record<AreaLevel, string> = {
  national: '/national',
  state: '/states',
  lga: '/lgas',
  ward: '/wards',
}

export function areaPath(level: AreaLevel, areaId: string | undefined, electionId: string) {
  const base = level === 'national' ? AREA_PATH.national : `${AREA_PATH[level]}/${encodeURIComponent(areaId ?? '')}`
  return buildPath(base, { election_id: electionId })
}

function scopeParams(level: AreaLevel, areaId: string | undefined) {
  return level === 'national' ? {} : { [`${level}_id`]: areaId }
}

export function useArea(level: AreaLevel, areaId: string | undefined, electionId: string | undefined) {
  return useAnalyticsQuery<AreaResponse>(
    areaPath(level, areaId, electionId ?? ''),
    Boolean(electionId) && (level === 'national' || Boolean(areaId)),
  )
}

export function usePartyResults(level: AreaLevel, areaId: string | undefined, electionId: string | undefined) {
  return useAnalyticsQuery<PartyResultsResponse>(
    buildPath('/party-results', { election_id: electionId, ...scopeParams(level, areaId) }),
    Boolean(electionId),
  )
}

export function useProgress(level: AreaLevel, areaId: string | undefined, electionId: string | undefined) {
  return useAnalyticsQuery<ProgressResponse>(
    buildPath('/progress', { election_id: electionId, ...scopeParams(level, areaId) }),
    Boolean(electionId),
  )
}

export type RecordFilters = {
  level: AreaLevel
  areaId?: string
  kind?: DiscrepancyKind
  status?: UnitResultStatus
  page: number
}

/** Polling units behind a total. A `kind` selects the discrepancy view; otherwise all units, optionally by status. */
export function usePollingUnitRecords(filters: RecordFilters, electionId: string | undefined) {
  const scope = scopeParams(filters.level, filters.areaId)
  const path = filters.kind
    ? buildPath('/discrepancies', { election_id: electionId, kind: filters.kind, page: filters.page, ...scope })
    : buildPath('/polling-units', { election_id: electionId, status: filters.status, page: filters.page, ...scope })
  return useAnalyticsQuery<PollingUnitPage>(path, Boolean(electionId))
}

export function useStateCoverage(electionId: string | undefined) {
  return useAnalyticsQuery<AreaListResponse>(buildPath('/states', { election_id: electionId }), Boolean(electionId))
}

export function usePollingUnitResult(unitId: string | undefined, electionId: string | undefined) {
  return useAnalyticsQuery<PollingUnitResultResponse>(
    buildPath(`/polling-units/${encodeURIComponent(unitId ?? '')}`, { election_id: electionId }),
    Boolean(unitId && electionId),
  )
}

type ChangeEvent = {
  election_id: string
  polling_unit_id: string
  ward_id: string
  lga_id: string
  state_id: string
}

/** Area-specific paths are refetched only when the change falls inside that area. */
export function affectedBy(path: string, change: ChangeEvent) {
  const match = /^\/(states|lgas|wards|polling-units)\/([^/?]+)/.exec(path)
  if (!match) return path.includes(change.election_id)
  return [change.state_id, change.lga_id, change.ward_id, change.polling_unit_id].includes(match[2] ?? '')
}

export type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'unavailable'

/**
 * Subscribes to server-sent aggregation changes and refetches only affected queries.
 * Events carry identifiers, never figures: totals always come from the API.
 */
export function useLiveAnalytics(electionId: string | undefined): LiveStatus {
  const queryClient = useQueryClient()
  const supported = typeof window !== 'undefined' && 'EventSource' in window
  const [status, setStatus] = useState<LiveStatus>('connecting')
  const pending = useRef<ChangeEvent[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (!supported || !electionId) return
    const source = new EventSource(buildPath(`${env.apiBaseUrl}/analytics/updates`, { election_id: electionId }))
    const refetchAll = () => void queryClient.invalidateQueries({ queryKey: [ANALYTICS_KEY] })
    const flush = () => {
      const changes = pending.current
      pending.current = []
      void queryClient.invalidateQueries({
        queryKey: [ANALYTICS_KEY],
        predicate: (query) => {
          const path = String(query.queryKey[1] ?? '')
          return changes.some((change) => affectedBy(path, change))
        },
      })
    }
    source.addEventListener('ready', () => {
      setStatus('live')
      refetchAll()
    })
    source.addEventListener('resync', refetchAll)
    source.addEventListener('aggregation', (event) => {
      try {
        pending.current.push(JSON.parse((event as MessageEvent<string>).data) as ChangeEvent)
      } catch {
        return
      }
      clearTimeout(timer.current)
      timer.current = setTimeout(flush, LIVE_DEBOUNCE_MS)
    })
    source.onerror = () => setStatus(source.readyState === EventSource.CLOSED ? 'unavailable' : 'reconnecting')
    return () => {
      clearTimeout(timer.current)
      source.close()
    }
  }, [electionId, queryClient, supported])

  return supported && electionId ? status : 'unavailable'
}
