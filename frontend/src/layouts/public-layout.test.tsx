import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PUBLIC_NAV, REPORT_INCIDENT_NAV } from '@/app/navigation'
import { installMockApi } from '@/test/mock-api'
import { makeAuthState, renderRoute } from '@/test/render'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('public layout', () => {
  it('offers every destination in the mobile menu and closes after navigating', async () => {
    const user = userEvent.setup()
    installMockApi()
    const { router } = renderRoute('/')
    await user.click(await screen.findByRole('button', { name: 'More' }))
    const mobileNav = await screen.findByRole('navigation', { name: 'Mobile' })
    for (const item of [...PUBLIC_NAV, REPORT_INCIDENT_NAV]) {
      expect(within(mobileNav).getByRole('link', { name: item.label })).toHaveAttribute('href', item.to)
    }
    await user.click(within(mobileNav).getByRole('link', { name: 'Updates' }))
    expect(router.state.location.pathname).toBe('/updates')
    expect(screen.queryByRole('navigation', { name: 'Mobile' })).not.toBeInTheDocument()
  })

  it('shows the home page actions and latest updates', async () => {
    installMockApi()
    renderRoute('/')
    const actions = screen.getByRole('region', { name: 'Built for people on the ground' })
    for (const name of ['Find your polling unit', 'View results', 'Election updates', 'Report an incident']) {
      expect(within(actions).getByRole('link', { name: new RegExp(name) })).toBeInTheDocument()
    }
    expect(
      await screen.findByText('Demo: polling unit relocation confirmed', {}, { timeout: 8_000 }),
    ).toBeInTheDocument()
  })

  it('keeps staff pages behind sign-in for public visitors and observers', async () => {
    installMockApi()
    const { router } = renderRoute('/admin/polling-units')
    expect(await screen.findByLabelText('Password', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/admin/sign-in')
  })

  it('does not let observers reach polling-unit administration', async () => {
    installMockApi()
    renderRoute('/admin/polling-units', makeAuthState({ id: 'o1', email: 'o@example.ng', roles: ['observer'] }))
    expect(await screen.findByText('You do not have access to this area', {}, { timeout: 8_000 })).toBeInTheDocument()
  })
})
