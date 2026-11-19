import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { AuthProvider } from '@/features/auth/auth-provider'
import { PUBLIC_QUERY_KEY } from '@/features/directory/api'
import { EvidenceSyncRunner } from '@/features/evidence/evidence-sync-runner'
import { IncidentSyncRunner } from '@/features/public/incidents/incident-sync-runner'
import { LocaleProvider } from '@/i18n/locale-provider'
import { startSyncEngine } from '@/lib/offline/sync-engine'
import { createQueryClient } from '@/lib/query-client'

export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient())
  useEffect(
    () => startSyncEngine(() => void client.invalidateQueries({ queryKey: [PUBLIC_QUERY_KEY] })),
    [client],
  )
  return (
    <QueryClientProvider client={client}>
      <LocaleProvider>
        <AuthProvider>
          <EvidenceSyncRunner />
          <IncidentSyncRunner />
          {children}
        </AuthProvider>
      </LocaleProvider>
    </QueryClientProvider>
  )
}
