import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

/** Mirrors backend `HealthResponse` (backend/app/schemas/health.py). */
export type HealthResponse = {
  status: 'ok' | 'degraded'
  service: string
  version: string
  environment: string
  database: 'ok' | 'unavailable' | 'not_configured'
}

export const systemKeys = {
  health: ['system', 'health'] as const,
}

export function useHealthQuery() {
  return useQuery({
    queryKey: systemKeys.health,
    queryFn: () => api.get<HealthResponse>('/health', { auth: false }),
    staleTime: 30_000,
  })
}
