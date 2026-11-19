import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type {
  ElectionUpdate,
  ItemResponse,
  Lga,
  ListResponse,
  PageResponse,
  PollingUnitDetail,
  PollingUnitStatus,
  PollingUnitSummary,
  State,
  UpdateCategory,
  UpdateVerificationStatus,
  Ward,
} from '@/features/directory/types'
import { fetchPublic, type Timestamped } from '@/lib/offline/public-cache'
import { queueRefresh } from '@/lib/offline/sync-engine'

export const PUBLIC_QUERY_KEY = 'public'

type Params = Record<string, string | number | null | undefined>

export function buildPath(base: string, params: Params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params).sort(([a], [b]) => a.localeCompare(b))) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${base}?${query}` : base
}

function usePublicQuery<T extends Timestamped>(path: string, enabled = true, keepPrevious = false) {
  return useQuery({
    queryKey: [PUBLIC_QUERY_KEY, path],
    queryFn: async () => {
      const result = await fetchPublic<T>(path)
      if (result.origin === 'cache') void queueRefresh(path)
      return result
    },
    enabled,
    placeholderData: keepPrevious ? keepPreviousData : undefined,
  })
}

export function useStates() {
  return usePublicQuery<ListResponse<State>>('/locations/states')
}

export function useLgas(stateId: string | undefined) {
  return usePublicQuery<ListResponse<Lga>>(buildPath('/locations/lgas', { state_id: stateId }), Boolean(stateId))
}

export function useWards(lgaId: string | undefined) {
  return usePublicQuery<ListResponse<Ward>>(buildPath('/locations/wards', { lga_id: lgaId }), Boolean(lgaId))
}

export type PollingUnitSearch = {
  stateId?: string
  lgaId?: string
  wardId?: string
  q?: string
  status?: PollingUnitStatus
  page?: number
  pageSize?: number
}

export function pollingUnitSearchPath(search: PollingUnitSearch) {
  return buildPath('/polling-units', {
    state_id: search.stateId,
    lga_id: search.lgaId,
    ward_id: search.wardId,
    q: search.q,
    status: search.status,
    page: search.page && search.page > 1 ? search.page : undefined,
    page_size: search.pageSize,
  })
}

export function usePollingUnitSearch(search: PollingUnitSearch, enabled: boolean) {
  return usePublicQuery<PageResponse<PollingUnitSummary>>(pollingUnitSearchPath(search), enabled, true)
}

export function usePollingUnit(id: string | undefined) {
  return usePublicQuery<ItemResponse<PollingUnitDetail>>(`/polling-units/${encodeURIComponent(id ?? '')}`, Boolean(id))
}

export type UpdateSearch = {
  category?: UpdateCategory
  verificationStatus?: UpdateVerificationStatus
  publishedFrom?: string
  publishedTo?: string
  page?: number
  pageSize?: number
}

export function useUpdates(search: UpdateSearch = {}, enabled = true) {
  return usePublicQuery<PageResponse<ElectionUpdate>>(
    buildPath('/updates', {
      category: search.category,
      verification_status: search.verificationStatus,
      published_from: search.publishedFrom,
      published_to: search.publishedTo,
      page: search.page && search.page > 1 ? search.page : undefined,
      page_size: search.pageSize,
    }),
    enabled,
    true,
  )
}

export function useUpdate(id: string | undefined) {
  return usePublicQuery<ItemResponse<ElectionUpdate>>(`/updates/${encodeURIComponent(id ?? '')}`, Boolean(id))
}
