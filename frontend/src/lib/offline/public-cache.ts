import { api, ApiError } from '@/lib/api-client'
import type { VeriVoteDatabase } from '@/lib/offline/db'

/** IndexedDB support is loaded on first use so it stays out of the initial bundle. */
export async function defaultDatabase(): Promise<VeriVoteDatabase> {
  return (await import('@/lib/offline/db')).db
}

/** Public responses all carry the server's generation time (see backend schemas/common.py). */
export type Timestamped = { generated_at: string }

export type CachedResult<T> = {
  data: T
  /** `network`: just received from the server. `cache`: read from this device. */
  origin: 'network' | 'cache'
  /** When this device last received the data from the server. */
  syncedAt: string
}

const MAX_ENTRIES = 300

function isOfflineError(error: unknown) {
  return error instanceof ApiError && (error.status === 0 || error.status === 429 || error.status >= 500)
}

/**
 * Fetches a public, read-only API path and keeps a copy on the device.
 *
 * - A response is only written if it is at least as new as the cached copy, so
 *   an out-of-order or replayed response never replaces newer server data.
 * - When the server is unreachable the cached copy is returned with
 *   `origin: 'cache'`; callers must present it as saved, not current.
 * - Client errors (404, 422) are never masked by the cache.
 */
export async function fetchPublic<T extends Timestamped>(
  path: string,
  database?: VeriVoteDatabase,
): Promise<CachedResult<T>> {
  let fresh: T
  try {
    fresh = await api.get<T>(path, { auth: false })
  } catch (error) {
    if (!isOfflineError(error)) throw error
    const cached = await readCache<T>(path, database)
    if (cached) return { data: cached.payload as T, origin: 'cache', syncedAt: cached.syncedAt }
    throw error
  }
  return storeIfNewer(path, fresh, database)
}

export async function storeIfNewer<T extends Timestamped>(
  path: string,
  fresh: T,
  maybeDatabase?: VeriVoteDatabase,
): Promise<CachedResult<T>> {
  const syncedAt = new Date().toISOString()
  try {
    const database = maybeDatabase ?? (await defaultDatabase())
    const kept = await database.transaction('rw', database.apiCache, async () => {
      const existing = await database.apiCache.get(path)
      if (existing && Date.parse(existing.generatedAt) > Date.parse(fresh.generated_at)) {
        return existing
      }
      await database.apiCache.put({ key: path, payload: fresh, generatedAt: fresh.generated_at, syncedAt })
      return null
    })
    if (kept) return { data: kept.payload as T, origin: 'network', syncedAt: kept.syncedAt }
    void pruneCache(database).catch(() => undefined)
  } catch {
    // Storage can be unavailable (private mode, quota). The live response is still valid.
  }
  return { data: fresh, origin: 'network', syncedAt }
}

async function readCache<T>(path: string, maybeDatabase?: VeriVoteDatabase) {
  try {
    const database = maybeDatabase ?? (await defaultDatabase())
    const entry = await database.apiCache.get(path)
    return entry as (typeof entry & { payload: T }) | undefined
  } catch {
    return undefined
  }
}

async function pruneCache(database: VeriVoteDatabase) {
  const count = await database.apiCache.count()
  if (count <= MAX_ENTRIES) return
  const oldest = await database.apiCache.orderBy('syncedAt').limit(count - MAX_ENTRIES).primaryKeys()
  await database.apiCache.bulkDelete(oldest)
}
