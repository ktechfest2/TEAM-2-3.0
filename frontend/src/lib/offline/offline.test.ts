import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, setAccessTokenProvider } from '@/lib/api-client'
import { VeriVoteDatabase } from '@/lib/offline/db'
import { fetchPublic, storeIfNewer } from '@/lib/offline/public-cache'
import { getSyncState, processOutbox, queueRefresh, resetSyncState } from '@/lib/offline/sync-engine'
import { installMockApi, installOfflineApi } from '@/test/mock-api'

let database: VeriVoteDatabase
let counter = 0

beforeEach(() => {
  database = new VeriVoteDatabase(`offline-test-${++counter}`)
  resetSyncState()
})

afterEach(async () => {
  await database.delete()
  vi.unstubAllGlobals()
  setAccessTokenProvider(async () => null)
})

describe('public cache', () => {
  it('stores live responses and serves them when offline', async () => {
    installMockApi()
    const live = await fetchPublic<{ generated_at: string }>('/locations/states', database)
    expect(live.origin).toBe('network')

    installOfflineApi()
    const offline = await fetchPublic<{ generated_at: string; items: unknown[] }>('/locations/states', database)
    expect(offline.origin).toBe('cache')
    expect(offline.syncedAt).toBe(live.syncedAt)
    expect(offline.data.items).toHaveLength(2)
  })

  it('fails clearly when offline with nothing saved', async () => {
    installOfflineApi()
    await expect(fetchPublic('/locations/states', database)).rejects.toMatchObject({ code: 'network_error', status: 0 })
  })

  it('never replaces newer saved data with an older response', async () => {
    await storeIfNewer('/updates', { generated_at: '2026-11-18T12:00:00Z', marker: 'newer' }, database)
    const result = await storeIfNewer('/updates', { generated_at: '2026-11-18T08:00:00Z', marker: 'older' }, database)
    expect(result.data).toMatchObject({ marker: 'newer' })
    expect((await database.apiCache.get('/updates'))?.payload).toMatchObject({ marker: 'newer' })

    await storeIfNewer('/updates', { generated_at: '2026-11-18T13:00:00Z', marker: 'latest' }, database)
    expect((await database.apiCache.get('/updates'))?.payload).toMatchObject({ marker: 'latest' })
  })

  it('does not hide a not-found error behind saved data', async () => {
    await storeIfNewer('/polling-units/missing', { generated_at: '2026-11-18T12:00:00Z' }, database)
    installMockApi()
    await expect(fetchPublic('/polling-units/missing', database)).rejects.toBeInstanceOf(ApiError)
  })

  it('sends public lookups without credentials even when signed in', async () => {
    setAccessTokenProvider(async () => 'staff-access-token')
    const fetchMock = installMockApi()
    await fetchPublic('/polling-units?q=demo', database)
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
    expect(new Headers(init?.headers).has('Authorization')).toBe(false)
    expect(init?.credentials).toBe('omit')
  })
})

describe('sync engine', () => {
  it('queues each refresh once', async () => {
    await queueRefresh('/locations/states', database)
    await queueRefresh('/locations/states', database)
    expect(await database.outbox.count()).toBe(1)
    expect(getSyncState().pending).toBe(1)
  })

  it('replays queued refreshes on reconnect and reports success', async () => {
    installMockApi()
    await queueRefresh('/locations/states', database)
    const onSynced = vi.fn()
    await processOutbox({ database, onSynced })
    expect(await database.outbox.count()).toBe(0)
    expect(getSyncState()).toMatchObject({ phase: 'idle', pending: 0 })
    expect(getSyncState().lastSyncedAt).not.toBeNull()
    expect(onSynced).toHaveBeenCalledOnce()
    expect(await database.apiCache.get('/locations/states')).toBeDefined()
  })

  it('keeps entries and reports an error while the server is unreachable', async () => {
    await queueRefresh('/locations/states', database)
    await processOutbox({ database, fetcher: async () => ({ origin: 'cache' }) })
    const [entry] = await database.outbox.toArray()
    expect(entry?.attempts).toBe(1)
    expect(getSyncState()).toMatchObject({ phase: 'error', pending: 1 })
  })

  it('gives up on an entry after repeated failures', async () => {
    await queueRefresh('/locations/states', database)
    const failing = async () => {
      throw new Error('down')
    }
    for (let attempt = 0; attempt < 5; attempt += 1) await processOutbox({ database, fetcher: failing })
    expect(await database.outbox.count()).toBe(0)
  })
})
