import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installOfflineApi } from '@/test/mock-api'
import { renderRoute } from '@/test/render'

describe('report incident page', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders offline with the emergency notice and the device queue', async () => {
    installOfflineApi()
    renderRoute('/report-incident')
    expect(await screen.findByRole('heading', { level: 1, name: 'Report an incident' })).toBeInTheDocument()
    expect(screen.getByText('In danger? Get help first')).toBeInTheDocument()
    expect(await screen.findByText('Nothing on this device')).toBeInTheDocument()
  })
})
