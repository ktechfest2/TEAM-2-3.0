import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { buildPath } from '@/features/directory/api'
import type {
  IncidentDetail,
  IncidentFilters,
  IncidentPage,
  IncidentReviewInput,
  IncidentStats,
  IncidentTrack,
  PublicIncidentSummary,
} from '@/features/incidents/types'
import { api, apiBlob } from '@/lib/api-client'

/**
 * Incident reports are private. Staff responses stay in the in-memory query cache and
 * are never written to IndexedDB. Only the public summary is cacheable.
 */
export const INCIDENTS_KEY = 'incidents'

function filterParams(filters: IncidentFilters) {
  return {
    election_id: filters.electionId,
    state_id: filters.stateId,
    lga_id: filters.lgaId,
    ward_id: filters.wardId,
    category: filters.category,
    severity: filters.severity,
    status: filters.status,
    occurred_from: filters.occurredFrom,
    occurred_to: filters.occurredTo,
  }
}

export function useIncidentStats(filters: IncidentFilters) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'stats', filters],
    queryFn: () => api.get<IncidentStats>(buildPath('/incidents/stats', filterParams(filters))),
    placeholderData: keepPreviousData,
  })
}

export function useIncidentList(filters: IncidentFilters, page: number, queue: boolean) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'list', filters, page, queue],
    queryFn: () =>
      api.get<IncidentPage>(
        buildPath('/incidents', {
          ...filterParams(filters),
          queue: queue ? 'true' : undefined,
          page: page > 1 ? page : undefined,
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'detail', id],
    queryFn: () => api.get<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`),
  })
}

export function useIncidentAttachment(incidentId: string, attachmentId: string) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'attachment', incidentId, attachmentId],
    queryFn: async () => {
      const { blob, sha256 } = await apiBlob(
        `/incidents/${encodeURIComponent(incidentId)}/attachments/${encodeURIComponent(attachmentId)}`,
      )
      return { url: URL.createObjectURL(blob), sha256 }
    },
    staleTime: Infinity,
    gcTime: 60_000,
  })
}

export function useReviewIncident(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: IncidentReviewInput) => api.post<IncidentDetail>(`/incidents/${encodeURIComponent(id)}/review`, input),
    onSuccess: (detail) => {
      queryClient.setQueryData([INCIDENTS_KEY, 'detail', id], detail)
      void queryClient.invalidateQueries({ queryKey: [INCIDENTS_KEY, 'list'] })
      void queryClient.invalidateQueries({ queryKey: [INCIDENTS_KEY, 'stats'] })
    },
  })
}

export function useTrackIncident(reference: string | null) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'track', reference],
    queryFn: () => api.get<IncidentTrack>(`/incidents/track/${encodeURIComponent(reference ?? '')}`, { auth: false }),
    enabled: Boolean(reference),
    retry: false,
  })
}

export function usePublicIncidents(electionId: string | undefined) {
  return useQuery({
    queryKey: [INCIDENTS_KEY, 'public', electionId],
    queryFn: () =>
      api.get<PublicIncidentSummary>(buildPath('/public/incidents', { election_id: electionId }), { auth: false }),
    enabled: Boolean(electionId),
  })
}
