import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '@/app/routes'
import { AuthContext, type AuthState, type AuthUser } from '@/features/auth/auth-context'
import { LocaleProvider } from '@/i18n/locale-provider'
import { LOCALE_STORAGE_KEY } from '@/i18n/languages'

export function makeAuthState(user: AuthUser | null, overrides: Partial<AuthState> = {}): AuthState {
  return {
    status: user ? 'authenticated' : 'anonymous',
    user,
    isPreview: false,
    isConfigured: true,
    provider: 'local',
    signInWithPassword: async () => user ?? { id: 'signed-in', email: null, roles: [] },
    signOut: async () => {},
    ...overrides,
  }
}

export function renderRoute(path: string, auth: AuthState = makeAuthState(null)) {
  try {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY)
  } catch {
    /* jsdom */
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const result = render(
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <AuthContext.Provider value={auth}>
          <RouterProvider router={router} />
        </AuthContext.Provider>
      </LocaleProvider>
    </QueryClientProvider>,
  )
  return { ...result, router }
}
