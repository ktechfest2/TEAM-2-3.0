import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { displayStatus, isOfficialNotice } from '@/features/polling-units/status'
import { db } from '@/lib/offline/db'
import { resetSyncState } from '@/lib/offline/sync-engine'
import { installMockApi, installOfflineApi, POLLING_UNITS } from '@/test/mock-api'
import { renderRoute } from '@/test/render'

beforeEach(async () => {
  await db.apiCache.clear()
  await db.outbox.clear()
  resetSyncState()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function requestedPaths(fetchMock: ReturnType<typeof installMockApi>) {
  return fetchMock.mock.calls.map(([input]) => new URL(String(input)).pathname + new URL(String(input)).search)
}

describe('status rules', () => {
  const [, official] = POLLING_UNITS
  const notice = official!.official_notices[0]!

  it('treats only confirmed, sourced notices as official', () => {
    expect(isOfficialNotice(notice)).toBe(true)
    expect(isOfficialNotice({ ...notice, source_name: null })).toBe(false)
    expect(isOfficialNotice({ ...notice, source_name: '  ' })).toBe(false)
    expect(isOfficialNotice({ ...notice, verification_status: 'awaiting_confirmation' })).toBe(false)
  })

  it('never displays an official relocation without a confirmed source', () => {
    expect(displayStatus(official!)).toBe('officially_relocated')
    expect(displayStatus({ status: 'officially_relocated', official_notices: [] })).toBe('pending_verification')
    expect(
      displayStatus({ status: 'officially_relocated', official_notices: [{ ...notice, source_name: null }] }),
    ).toBe('pending_verification')
  })
})

describe('polling unit finder', () => {
  it('asks for a location or search before querying', async () => {
    const fetchMock = installMockApi()
    renderRoute('/polling-units')
    expect(await screen.findByText('Choose a state or enter a search', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(requestedPaths(fetchMock).some((path) => path.includes('/polling-units'))).toBe(false)
  })

  it('cascades state, LGA and ward selection', async () => {
    const user = userEvent.setup()
    const fetchMock = installMockApi()
    renderRoute('/polling-units')

    const state = await screen.findByLabelText('State', {}, { timeout: 8_000 })
    const lga = screen.getByLabelText('Local Government Area')
    const ward = screen.getByLabelText('Ward')
    expect(lga).toBeDisabled()
    expect(ward).toBeDisabled()

    await waitFor(() => expect(within(state).getByRole('option', { name: 'Lagos' })).toBeInTheDocument())
    await user.selectOptions(state, 'Lagos')
    await waitFor(() => expect(within(lga).getByRole('option', { name: 'Ikeja' })).toBeInTheDocument())
    expect(within(lga).queryByRole('option', { name: 'Abuja Municipal' })).not.toBeInTheDocument()
    expect(ward).toBeDisabled()

    await user.selectOptions(lga, 'Ikeja')
    await waitFor(() => expect(within(ward).getByRole('option', { name: 'Demo Ward A' })).toBeInTheDocument())
    await user.selectOptions(ward, 'Demo Ward A')

    expect(await screen.findByText(/Showing 1–4 of 4 polling units/, {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(requestedPaths(fetchMock)).toContain('/api/v1/polling-units?lga_id=l-ikj&page_size=10&state_id=s-lag&ward_id=w-a')

    await user.selectOptions(state, 'Federal Capital Territory')
    await waitFor(() => expect(screen.getByLabelText('Ward')).toBeDisabled())
    expect(screen.getByLabelText('Local Government Area')).toHaveValue('')
  })

  it('shows every required field for a search result', async () => {
    const user = userEvent.setup()
    installMockApi()
    renderRoute('/polling-units')
    await user.type(await screen.findByLabelText('Polling-unit name or code', {}, { timeout: 8_000 }), 'a01')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    const heading = await screen.findByRole('heading', { name: 'Demo Polling Unit A01 (fictional)' }, { timeout: 8_000 })
    const card = heading.closest('article')!
    const scope = within(card)
    expect(scope.getByText('DEMO-02-01-01-001')).toBeInTheDocument()
    expect(scope.getByText('Lagos')).toBeInTheDocument()
    expect(scope.getByText('Ikeja')).toBeInTheDocument()
    expect(scope.getByText('Demo Ward A')).toBeInTheDocument()
    expect(scope.getByText('Fictional address for demonstration')).toBeInTheDocument()
    expect(scope.getByText(/\(approximate\)/)).toBeInTheDocument()
    expect(scope.getByText('VoteTrace demonstration dataset (not INEC)')).toBeInTheDocument()
    expect(scope.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText(/Sample directory, not sourced from INEC/)).toBeInTheDocument()
  })

  it('rejects invalid search text without calling the API', async () => {
    const user = userEvent.setup()
    const fetchMock = installMockApi()
    renderRoute('/polling-units')
    const input = await screen.findByLabelText('Polling-unit name or code', {}, { timeout: 8_000 })

    await user.type(input, '<script>')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('Use letters, numbers, spaces and basic punctuation only.')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-invalid', 'true')

    await user.clear(input)
    await user.type(input, 'a')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('Enter at least 2 characters.')).toBeInTheDocument()
    expect(requestedPaths(fetchMock).some((path) => path.includes('/polling-units'))).toBe(false)
  })

  it('explains when nothing matches', async () => {
    installMockApi()
    renderRoute('/polling-units?q=nowhere')
    expect(await screen.findByText('No polling units match your search', {}, { timeout: 8_000 })).toBeInTheDocument()
  })

  it('shows a map fallback when results have no coordinates', async () => {
    installMockApi()
    renderRoute('/polling-units?q=a02')
    expect(
      await screen.findByText(/No map coordinates are available/, {}, { timeout: 8_000 }),
    ).toBeInTheDocument()
  })
})

describe('polling unit detail', () => {
  it('shows an official relocation with its source and reference', async () => {
    installMockApi()
    renderRoute('/polling-units/pu-official')
    expect(await screen.findByRole('heading', { level: 1, name: 'Demo Polling Unit A02 (fictional)' }, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getByText(/Relocation notice: officially confirmed/)).toBeInTheDocument()
    expect(screen.getByText('DEMO-REF-0001')).toBeInTheDocument()
    expect(screen.getByText('Demonstration notice (not an INEC announcement)')).toBeInTheDocument()
    expect(screen.queryByText('Official confirmation unavailable.')).not.toBeInTheDocument()
  })

  it('keeps crowd reports separate from official notices', async () => {
    installMockApi()
    renderRoute('/polling-units/pu-reported')
    expect(await screen.findByText(/Relocation reported by the public \(3 reports\)/, {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getByText(/not an official relocation notice and not an INEC announcement/)).toBeInTheDocument()
    expect(screen.getByText('Official confirmation unavailable.')).toBeInTheDocument()
    expect(screen.queryByText(/officially confirmed/)).not.toBeInTheDocument()
    expect(screen.getAllByText('Relocation reported').length).toBeGreaterThan(0)
  })

  it('marks an unsourced notice as unconfirmed', async () => {
    installMockApi()
    renderRoute('/polling-units/pu-closed')
    expect(
      await screen.findByText(/Temporary closure notice: Official confirmation unavailable\./, {}, { timeout: 8_000 }),
    ).toBeInTheDocument()
    expect(screen.getByText('No authoritative source provided')).toBeInTheDocument()
  })

  it('reports a missing polling unit', async () => {
    installMockApi()
    renderRoute('/polling-units/does-not-exist')
    expect(await screen.findByRole('heading', { level: 1, name: 'Polling unit not found' }, { timeout: 8_000 })).toBeInTheDocument()
  })

  it('shows saved data offline and labels it as possibly out of date', async () => {
    installMockApi()
    const first = renderRoute('/polling-units/pu-active')
    await screen.findByRole('heading', { level: 1, name: 'Demo Polling Unit A01 (fictional)' }, { timeout: 8_000 })
    expect(screen.getByText(/^Last synced/)).toBeInTheDocument()
    first.unmount()

    installOfflineApi()
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    renderRoute('/polling-units/pu-active')
    expect(await screen.findByText(/Saved copy from/, {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Demo Polling Unit A01 (fictional)' })).toBeInTheDocument()
    expect(screen.getByText(/You are offline/)).toBeInTheDocument()
    expect(screen.getByText(/The map is unavailable offline/)).toBeInTheDocument()
    await waitFor(async () => expect(await db.outbox.count()).toBe(1))
  })

  it('explains when a polling unit was never saved for offline use', async () => {
    installOfflineApi()
    renderRoute('/polling-units/pu-active')
    expect(
      await screen.findByText(/You are offline and this polling unit has not been saved/, {}, { timeout: 8_000 }),
    ).toBeInTheDocument()
  })
})
