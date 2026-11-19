/**
 * Role model shared conceptually with backend/app/db/enums.py.
 * Keep both lists in sync. Frontend checks are a UX convenience only;
 * the backend and RLS policies are the enforcement boundary.
 */
export const ROLES = ['observer', 'party_agent', 'reviewer', 'auditor', 'election_admin', 'system_admin'] as const

export type Role = (typeof ROLES)[number]

export const ROLE_LABELS: Record<Role, string> = {
  observer: 'Field observer',
  party_agent: 'Party agent',
  reviewer: 'Verification reviewer',
  auditor: 'Auditor',
  election_admin: 'Election administrator',
  system_admin: 'System administrator',
}

/** Roles permitted to enter the administrative dashboard at all. */
export const ADMIN_CONSOLE_ROLES: readonly Role[] = ['reviewer', 'auditor', 'election_admin', 'system_admin']

/** Mirrors backend EVIDENCE_SUBMITTER_ROLES. */
export const EVIDENCE_SUBMITTER_ROLES: readonly Role[] = ['observer', 'party_agent', 'election_admin', 'system_admin']
/** Mirrors backend EVIDENCE_STAFF_ROLES: may read every submission. */
export const EVIDENCE_STAFF_ROLES: readonly Role[] = ['reviewer', 'auditor', 'election_admin', 'system_admin']
/** Mirrors backend EVIDENCE_REVIEWER_ROLES: may approve or reject. Auditors are read-only. */
export const EVIDENCE_REVIEWER_ROLES: readonly Role[] = ['reviewer', 'election_admin']

export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && (ROLES as readonly string[]).includes(value)
}

/** Extract roles from Supabase `app_metadata`, which only the service role can write. */
export function rolesFromAppMetadata(appMetadata: Record<string, unknown> | undefined): Role[] {
  const raw = appMetadata?.roles
  if (!Array.isArray(raw)) return []
  return raw.filter(isRole)
}

export function hasAnyRole(userRoles: readonly Role[], allowed: readonly Role[]) {
  return allowed.length === 0 || userRoles.some((role) => allowed.includes(role))
}
