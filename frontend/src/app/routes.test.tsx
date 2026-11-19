import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ADMIN_NAV, PUBLIC_NAV, REPORT_INCIDENT_NAV } from '@/app/navigation'
import { ROLES } from '@/features/auth/roles'
import { makeAuthState, renderRoute } from '@/test/render'

vi.stubGlobal(
  'fetch',
  vi.fn(() => Promise.reject(new TypeError('offline in tests'))),
)

const superUser = makeAuthState({ id: 'u1', email: 'admin@example.ng', roles: [...ROLES] })

describe('public routes', () => {
  it('renders the home page with the tagline', async () => {
    renderRoute('/')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/verifiable evidence/i)
    expect(screen.getAllByText('Every Vote, Every Voice.').length).toBeGreaterThan(0)
  })

  it.each([...PUBLIC_NAV, REPORT_INCIDENT_NAV].map((item) => [item.to]))(
    'resolves %s',
    async (path) => {
      renderRoute(path)
      expect(await screen.findByRole('heading', { level: 1 }, { timeout: 8_000 })).toBeInTheDocument()
      expect(screen.queryByText('Page not found')).not.toBeInTheDocument()
    },
    10_000,
  )

  it('shows a not-found page for unknown paths', async () => {
    renderRoute('/does-not-exist')
    expect(await screen.findByText('Page not found')).toBeInTheDocument()
  })
})

describe('admin routes', () => {
  it('redirects anonymous visitors to sign-in', async () => {
    const { router } = renderRoute('/admin/results')
    expect(await screen.findByLabelText('Password')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/admin/sign-in')
  })

  it('blocks authenticated users without an admin role', async () => {
    renderRoute('/admin', makeAuthState({ id: 'u2', email: 'obs@example.ng', roles: ['observer'] }))
    expect(await screen.findByText('You do not have access to this area')).toBeInTheDocument()
  })

  it('blocks a reviewer from system settings', async () => {
    renderRoute('/admin/settings', makeAuthState({ id: 'u3', email: 'rev@example.ng', roles: ['reviewer'] }))
    expect(await screen.findByText('You do not have access to this area')).toBeInTheDocument()
  })

  it('hides navigation entries the user cannot access', async () => {
    renderRoute('/admin', makeAuthState({ id: 'u4', email: 'aud@example.ng', roles: ['auditor'] }))
    const sidebar = await screen.findAllByRole('navigation', { name: 'Administration' })
    expect(sidebar[0]).toHaveTextContent('Audit logs')
    expect(sidebar[0]).not.toHaveTextContent('Settings')
  })

  it.each(ADMIN_NAV.map((item) => [item.to, item.label]))(
    'resolves %s for an authorised user',
    async (path, label) => {
      renderRoute(path, superUser)
      expect(await screen.findByRole('heading', { level: 1, name: label }, { timeout: 8_000 })).toBeInTheDocument()
    },
    10_000,
  )
})
