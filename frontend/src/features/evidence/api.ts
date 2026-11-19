import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { buildPath, PUBLIC_QUERY_KEY } from '@/features/directory/api'
import type { ListResponse } from '@/features/directory/types'
import type {
  AnomalyReport,
  AuditTrail,
  Comparison,
  Election,
  EvidenceDetail,
  EvidencePage,
  EvidenceStatus,
  Extraction,
  FieldCorrection,
  IntegrityReport,
  ReviewAction,
  ReviewOutcome,
  Validation,
} from '@/features/evidence/types'
import { api, apiBlob } from '@/lib/api-client'
import { fetchPublic } from '@/lib/offline/public-cache'

/**
 * Evidence data is private. It is held only in the in-memory query cache and is
 * never written to IndexedDB (unlike public directory responses).
 */
export const EVIDENCE_KEY = 'evidence'

export function useElections() {
  return useQuery({
    queryKey: [PUBLIC_QUERY_KEY, '/elections'],
    queryFn: () => fetchPublic<ListResponse<Election>>('/elections'),
  })
}

export type EvidenceListFilters = {
  status?: EvidenceStatus
  queue?: 'review'
  mine?: boolean
  electionId?: string
  pollingUnitId?: string
  page?: number
}

export function evidenceListPath(filters: EvidenceListFilters) {
  return buildPath('/evidence', {
    status: filters.status,
    queue: filters.queue,
    mine: filters.mine ? 'true' : undefined,
    election_id: filters.electionId,
    polling_unit_id: filters.pollingUnitId,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  })
}

export function useEvidenceList(filters: EvidenceListFilters, enabled = true) {
  return useQuery({
    queryKey: [EVIDENCE_KEY, 'list', filters],
    queryFn: () => api.get<EvidencePage>(evidenceListPath(filters)),
    enabled,
  })
}

const detailKey = (id: string, part: string) => [EVIDENCE_KEY, id, part]

export function useEvidence(id: string) {
  return useQuery({ queryKey: detailKey(id, 'detail'), queryFn: () => api.get<EvidenceDetail>(`/evidence/${id}`) })
}

export function useEvidenceImage(id: string, variant: 'original' | 'processed', enabled = true) {
  return useQuery({
    queryKey: detailKey(id, `image-${variant}`),
    queryFn: () => apiBlob(`/evidence/${id}/image?variant=${variant}`),
    enabled,
    staleTime: Infinity,
    retry: false,
  })
}

/** Resolves to null when the evidence has not reached that stage yet (404). */
function optional<T>(load: () => Promise<T>) {
  return async () => {
    try {
      return await load()
    } catch (error) {
      if (error instanceof Error && 'status' in error && (error as { status: number }).status === 404) return null
      throw error
    }
  }
}

export function useExtraction(id: string) {
  return useQuery({
    queryKey: detailKey(id, 'extraction'),
    queryFn: optional(() => api.get<Extraction>(`/evidence/${id}/extraction`)),
  })
}

export function useValidation(id: string) {
  return useQuery({
    queryKey: detailKey(id, 'validation'),
    queryFn: optional(() => api.get<Validation>(`/evidence/${id}/validation`)),
  })
}

export function useComparisons(id: string, enabled: boolean) {
  return useQuery({
    queryKey: detailKey(id, 'comparisons'),
    queryFn: () => api.get<Comparison[]>(`/evidence/${id}/comparisons`),
    enabled,
  })
}

export function useAnomalies(id: string, enabled: boolean) {
  return useQuery({
    queryKey: detailKey(id, 'anomalies'),
    queryFn: () => api.get<AnomalyReport>(`/evidence/${id}/anomalies`),
    enabled,
  })
}

export function useAudit(id: string) {
  return useQuery({ queryKey: detailKey(id, 'audit'), queryFn: () => api.get<AuditTrail>(`/evidence/${id}/audit`) })
}

export function useIntegrity(id: string, enabled: boolean) {
  return useQuery({
    queryKey: detailKey(id, 'integrity'),
    queryFn: () => api.get<IntegrityReport>(`/evidence/${id}/integrity`),
    enabled,
  })
}

function useInvalidateEvidence(id: string) {
  const queryClient = useQueryClient()
  return () =>
    queryClient.invalidateQueries({
      predicate: (query) =>
        query.queryKey[0] === EVIDENCE_KEY &&
        (query.queryKey[1] === id || query.queryKey[1] === 'list') &&
        !String(query.queryKey[2] ?? '').startsWith('image-original'),
    })
}

export function useProcessEvidence(id: string) {
  const invalidate = useInvalidateEvidence(id)
  return useMutation({
    mutationFn: () => api.post<Extraction>(`/evidence/${id}/process`),
    onSettled: invalidate,
  })
}

export function useCorrectExtraction(id: string) {
  const invalidate = useInvalidateEvidence(id)
  return useMutation({
    mutationFn: (corrections: FieldCorrection[]) =>
      api.patch<Extraction>(`/evidence/${id}/extraction`, { corrections }),
    onSettled: invalidate,
  })
}

export function useValidateEvidence(id: string) {
  const invalidate = useInvalidateEvidence(id)
  return useMutation({
    mutationFn: () => api.post<Validation>(`/evidence/${id}/validate`),
    onSettled: invalidate,
  })
}

export function useReviewEvidence(id: string) {
  const invalidate = useInvalidateEvidence(id)
  return useMutation({
    mutationFn: (input: { action: ReviewAction; notes?: string }) =>
      api.post<ReviewOutcome>(`/evidence/${id}/review`, input),
    onSettled: invalidate,
  })
}
