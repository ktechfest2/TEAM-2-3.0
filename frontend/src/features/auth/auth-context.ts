import { createContext, useContext } from 'react'
import type { Role } from '@/features/auth/roles'

export type AuthUser = {
  id: string
  email: string | null
  roles: Role[]
  /** A temporary password is in use. The account has no roles until it is changed. */
  mustChangePassword?: boolean
}

export type AuthState = {
  status: 'loading' | 'authenticated' | 'anonymous'
  user: AuthUser | null
  /** True when the dev-only admin preview principal is active. */
  isPreview: boolean
  isConfigured: boolean
  /** "local" uses VoteTrace's own accounts; "supabase" when a Supabase project is configured. */
  provider?: 'local' | 'supabase'
  signInWithPassword: (email: string, password: string) => Promise<AuthUser>
  changePassword?: (currentPassword: string, newPassword: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within <AuthProvider>')
  return context
}
