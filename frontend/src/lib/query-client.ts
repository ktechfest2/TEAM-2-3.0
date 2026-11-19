import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/lib/api-client'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        gcTime: 10 * 60_000,
        refetchOnWindowFocus: false,
        networkMode: 'offlineFirst',
        retry: (failureCount, error) => {
          // Client errors (4xx) will not succeed on retry.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
          return failureCount < 2
        },
      },
      mutations: {
        networkMode: 'offlineFirst',
        retry: false,
      },
    },
  })
}
