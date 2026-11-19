import { api } from '@/lib/api-client'
import type { AuthUser } from '@/features/auth/auth-context'
import { ROLES, type Role } from '@/features/auth/roles'

const STORAGE_KEY = 'verivote.session'

export type StoredSession = { token: string; expiresAt: string }

export type AccountResponse = {
  id: string
  email: string
  display_name: string | null
  roles: string[]
  is_active: boolean
  has_password: boolean
  must_change_password: boolean
  last_sign_in_at: string | null
  created_at: string | null
}

export type SessionResponse = {
  access_token: string
  token_type: string
  expires_at: string
  account: AccountResponse
}

type PrincipalResponse = {
  user_id: string
  email: string | null
  roles: string[]
  must_change_password?: boolean
}

function knownRoles(values: string[]): Role[] {
  return values.filter((value): value is Role => (ROLES as readonly string[]).includes(value))
}

export function readStoredSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredSession>
    if (typeof parsed.token !== 'string' || typeof parsed.expiresAt !== 'string') return null
    if (Date.parse(parsed.expiresAt) <= Date.now()) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return { token: parsed.token, expiresAt: parsed.expiresAt }
  } catch {
    return null
  }
}

export function storeSession(session: StoredSession | null) {
  if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  else localStorage.removeItem(STORAGE_KEY)
}

export function userFromAccount(account: AccountResponse): AuthUser {
  return {
    id: account.id,
    email: account.email,
    roles: knownRoles(account.roles),
    mustChangePassword: account.must_change_password,
  }
}

export async function signIn(email: string, password: string): Promise<SessionResponse> {
  return api.post<SessionResponse>('/auth/login', { email, password }, { auth: false })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<SessionResponse> {
  return api.post<SessionResponse>('/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function fetchPrincipal(): Promise<AuthUser> {
  const principal = await api.get<PrincipalResponse>('/auth/me')
  return {
    id: principal.user_id,
    email: principal.email,
    roles: knownRoles(principal.roles),
    mustChangePassword: Boolean(principal.must_change_password),
  }
}
