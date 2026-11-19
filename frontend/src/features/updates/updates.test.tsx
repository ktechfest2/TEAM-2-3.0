import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { db } from '@/lib/offline/db'
import { installMockApi } from '@/test/mock-api'
import { renderRoute } from '@/test/render'

beforeEach(async () => {
  await db.apiCache.clear()
  await db.outbox.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('election updates', () => {
  it('distinguishes official, independently verified and reported updates', async () => {
    installMockApi()
    renderRoute('/updates')
    const list = await screen.findByRole('list', { name: 'Election updates' }, { timeout: 8_000 })
    const items = within(list).getAllByRole('article')
    expect(items).toHaveLength(3)
    expect(within(items[0]!).getByText('Officially confirmed')).toBeInTheDocument()
    expect(within(items[1]!).getByText('Independently verified')).toBeInTheDocument()
    expect(within(items[2]!).getByText('Reported, awaiting verification')).toBeInTheDocument()
    expect(within(items[2]!).getByText('Not an official announcement.')).toBeInTheDocument()
  })

  it('filters by category', async () => {
    const user = userEvent.setup()
    const fetchMock = installMockApi()
    renderRoute('/updates')
    await screen.findByRole('list', { name: 'Election updates' }, { timeout: 8_000 })
    await user.selectOptions(screen.getByLabelText('Category'), 'Voting delay')
    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1))
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('category=voting_delay'))).toBe(true)
  })

  it('sends date filters and rejects a reversed range', async () => {
    const fetchMock = installMockApi()
    renderRoute('/updates?from=2026-11-10&to=2026-11-01')
    expect(
      await screen.findAllByText('The start date must be on or before the end date.', {}, { timeout: 8_000 }),
    ).not.toHaveLength(0)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/updates'))).toBe(false)
  })

  it('passes a valid date range to the API', async () => {
    const fetchMock = installMockApi()
    renderRoute('/updates?from=2026-11-01&to=2026-11-10')
    await screen.findByRole('list', { name: 'Election updates' }, { timeout: 8_000 })
    const url = fetchMock.mock.calls.map(([input]) => String(input)).find((input) => input.includes('/updates'))!
    const params = new URL(url).searchParams
    expect(params.get('published_from')).toBe(new Date('2026-11-01T00:00:00').toISOString())
    expect(params.get('published_to')).toBe(new Date('2026-11-10T23:59:59.999').toISOString())
  })

  it('warns that a reported update is not an INEC announcement', async () => {
    installMockApi()
    renderRoute('/updates/u-reported')
    expect(await screen.findByRole('heading', { level: 1, name: 'Demo: unconfirmed relocation report' }, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getByText('Not an INEC announcement')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View the affected polling unit' })).toHaveAttribute(
      'href',
      '/polling-units/pu-reported',
    )
  })

  it('does not add the INEC warning to officially confirmed updates', async () => {
    installMockApi()
    renderRoute('/updates/u-official')
    expect(await screen.findByText('DEMO-REF-0001', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.queryByText('Not an INEC announcement')).not.toBeInTheDocument()
  })
})
