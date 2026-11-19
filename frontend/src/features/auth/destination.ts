import type { AuthUser } from '@/features/auth/auth-context'
import { ADMIN_CONSOLE_ROLES, EVIDENCE_SUBMITTER_ROLES, hasAnyRole } from '@/features/auth/roles'

export const SIGN_IN_PATH = '/admin/sign-in'
export const CHANGE_PASSWORD_PATH = '/account/password'

/** Same-site paths only, and never back to the auth pages themselves. */
export function safeReturnPath(from: unknown): string | null {
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return null
  if (from.startsWith(SIGN_IN_PATH) || from.startsWith(CHANGE_PASSWORD_PATH)) return null
  return from
}

/** Where a user goes after signing in: the page they asked for, or their home area. */
export function destinationFor(user: AuthUser, from: unknown): string {
  if (user.mustChangePassword) return CHANGE_PASSWORD_PATH
  const requested = safeReturnPath(from)
  if (requested) return requested
  if (hasAnyRole(user.roles, ADMIN_CONSOLE_ROLES)) return '/admin'
  if (hasAnyRole(user.roles, EVIDENCE_SUBMITTER_ROLES)) return '/evidence'
  return '/'
}
