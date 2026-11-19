import { useSyncExternalStore } from 'react'
import type { VeriVoteDatabase } from '@/lib/offline/db'
import { defaultDatabase, fetchPublic } from '@/lib/offline/public-cache'

/**
 * Replays queued work when the device reconnects. Only safe, idempotent
 * actions are queued: re-fetching public read-only data the user viewed
 * offline. Incident drafts stay on the device until submission exists.
 */

export type SyncPhase = 'idle' | 'syncing' | 'error'

export type SyncState = {
  phase: SyncPhase
  pending: number
  lastSyncedAt: string | null
  lastError: string | null
}

const MAX_ATTEMPTS = 5
const INITIAL: SyncState = { phase: 'idle', pending: 0, lastSyncedAt: null, lastError: null }

let state: SyncState = INITIAL
const listeners = new Set<() => void>()

function setState(next: Partial<SyncState>) {
  state = { ...state, ...next }
  listeners.forEach((listener) => listener())
}

export function getSyncState() {
  return state
}

export function resetSyncState() {
  state = INITIAL
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useSyncState() {
  return useSyncExternalStore(subscribe, getSyncState, getSyncState)
}

async function countPending(database: VeriVoteDatabase) {
  return database.outbox.where('entityType').equals('public_refresh').count()
}

/** Queue a re-fetch of a public API path for when the connection returns. Deduplicated per path. */
export async function queueRefresh(path: string, maybeDatabase?: VeriVoteDatabase) {
  try {
    const database = maybeDatabase ?? (await defaultDatabase())
    const existing = await database.outbox.where('[entityType+entityId]').equals(['public_refresh', path]).first()
    if (!existing) {
      await database.outbox.add({
        entityType: 'public_refresh',
        entityId: path,
        createdAt: new Date().toISOString(),
        attempts: 0,
      })
    }
    setState({ pending: await countPending(database) })
  } catch {
    // Storage unavailable: nothing to replay later, which is safe.
  }
}

type ProcessOptions = {
  database?: VeriVoteDatabase
  fetcher?: (path: string) => Promise<{ origin: 'network' | 'cache' }>
  onSynced?: () => void
}

let running: Promise<void> | null = null

export function processOutbox(options: ProcessOptions = {}): Promise<void> {
  running ??= run(options).finally(() => {
    running = null
  })
  return running
}

async function run({ database: maybeDatabase, fetcher, onSynced }: ProcessOptions) {
  const database = maybeDatabase ?? (await defaultDatabase())
  const fetchPath = fetcher ?? ((path: string) => fetchPublic(path, database))
  const entries = await database.outbox.where('entityType').equals('public_refresh').toArray()
  if (entries.length === 0) {
    setState({ pending: 0, phase: state.phase === 'syncing' ? 'idle' : state.phase })
    return
  }

  setState({ phase: 'syncing', pending: entries.length, lastError: null })
  let failed = 0
  let lastError: string | null = null

  for (const entry of entries) {
    try {
      const result = await fetchPath(entry.entityId)
      // A cache hit means the server is still unreachable; keep the entry.
      if (result.origin !== 'network') throw new Error('Server unreachable')
      await database.outbox.delete(entry.id!)
    } catch (error) {
      failed += 1
      lastError = error instanceof Error ? error.message : 'Sync failed'
      const attempts = entry.attempts + 1
      if (attempts >= MAX_ATTEMPTS) {
        await database.outbox.delete(entry.id!)
      } else {
        await database.outbox.update(entry.id!, { attempts, lastError })
      }
    }
  }

  const pending = await countPending(database)
  if (failed === 0) {
    setState({ phase: 'idle', pending, lastSyncedAt: new Date().toISOString(), lastError: null })
  } else {
    setState({ phase: 'error', pending, lastError })
  }
  if (failed < entries.length) onSynced?.()
}

/** Starts replaying the outbox on reconnect. Returns a cleanup function. */
export function startSyncEngine(onSynced: () => void, database?: VeriVoteDatabase) {
  const sync = () => void processOutbox({ database, onSynced }).catch(() => setState({ phase: 'error' }))
  window.addEventListener('online', sync)
  void (database ? Promise.resolve(database) : defaultDatabase())
    .then(countPending)
    .then((pending) => setState({ pending }))
    .catch(() => undefined)
  if (navigator.onLine) sync()
  return () => window.removeEventListener('online', sync)
}
