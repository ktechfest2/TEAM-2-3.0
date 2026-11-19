import { describe, expect, it } from 'vitest'
import { hasAnyRole, rolesFromAppMetadata } from '@/features/auth/roles'

describe('rolesFromAppMetadata', () => {
  it('returns only recognised roles', () => {
    expect(rolesFromAppMetadata({ roles: ['reviewer', 'superuser', 42] })).toEqual(['reviewer'])
  })

  it('returns no roles for missing or malformed metadata', () => {
    expect(rolesFromAppMetadata(undefined)).toEqual([])
    expect(rolesFromAppMetadata({ roles: 'system_admin' })).toEqual([])
  })
})

describe('hasAnyRole', () => {
  it('requires at least one overlapping role', () => {
    expect(hasAnyRole(['reviewer'], ['reviewer', 'election_admin'])).toBe(true)
    expect(hasAnyRole(['observer'], ['system_admin'])).toBe(false)
    expect(hasAnyRole([], ['observer'])).toBe(false)
  })
})
