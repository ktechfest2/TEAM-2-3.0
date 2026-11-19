import { useSyncExternalStore } from 'react'
import type { SubmissionReceipt } from '@/features/evidence/types'
import { ApiError, apiRequest } from '@/lib/api-client'
import type { EvidenceDraft, VeriVoteDatabase } from '@/lib/offline/db'
import { defaultDatabase } from '@/lib/offline/public-cache'

/**
 * Offline evidence queue. Photos are saved on the device first, then uploaded with
 * the draft's local ID as the Idempotency-Key, so a retry after a dropped
 * connection returns the original server record instead of creating a duplicate.
 * A draft is shown as received only after the server confirms it.
 */

export type NewDraft = Omit<
  EvidenceDraft,
  'localId' | 'createdAt' | 'uploadStatus' | 'attempts' | 'serverId' | 'serverReceivedAt'
>

export type EvidenceSyncState = {
  running: boolean
  total: number
  completed: number
  currentId: string | null
  lastError: string | null
}

const INITIAL: EvidenceSyncState = { running: false, total: 0, completed: 0, currentId: null, lastError: null }
const MAX_AUTOMATIC_ATTEMPTS = 8
const listeners = new Set<() => void>()
let state = INITIAL

function setState(next: Partial<EvidenceSyncState>) {
  state = { ...state, ...next }
  listeners.forEach((listener) => listener())
}

export function useEvidenceSyncState() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => state,
    () => state,
  )
}

export function resetEvidenceSyncState() {
  state = INITIAL
}

export async function saveDraft(draft: NewDraft, database?: VeriVoteDatabase): Promise<EvidenceDraft> {
  const target = database ?? (await defaultDatabase())
  const record: EvidenceDraft = {
    ...draft,
    localId: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    uploadStatus: 'queued',
    attempts: 0,
  }
  await target.evidenceDrafts.add(record)
  return record
}

export async function listDrafts(database?: VeriVoteDatabase) {
  const target = database ?? (await defaultDatabase())
  return target.evidenceDrafts.orderBy('createdAt').reverse().toArray()
}

export async function discardDraft(localId: string, database?: VeriVoteDatabase) {
  const target = database ?? (await defaultDatabase())
  const draft = await target.evidenceDrafts.get(localId)
  // A confirmed submission lives on the server; removing the local copy is always safe.
  // An unconfirmed draft is removed only on explicit request.
  if (draft) await target.evidenceDrafts.delete(localId)
}

export async function retryDraft(localId: string, database?: VeriVoteDatabase) {
  const target = database ?? (await defaultDatabase())
  await target.evidenceDrafts.update(localId, {
    uploadStatus: 'queued',
    attempts: 0,
    lastError: undefined,
    permanentFailure: false,
  })
}

/** Errors worth retrying automatically: connectivity, rate limits and server faults. */
function isTransient(error: unknown) {
  if (!(error instanceof ApiError)) return true
  return error.status === 0 || error.status === 401 || error.status === 408 || error.status === 429 || error.status >= 500
}

export async function uploadDraft(draft: EvidenceDraft): Promise<SubmissionReceipt> {
  if (!draft.data) throw new Error('The photo is no longer stored on this device.')
  const form = new FormData()
  form.append('election_id', draft.electionId)
  form.append('polling_unit_id', draft.pollingUnitId)
  form.append('captured_at', draft.capturedAt)
  form.append('capture_source', draft.captureSource)
  form.append('file', new Blob([draft.data], { type: draft.contentType }), draft.fileName)
  return apiRequest<SubmissionReceipt>('/evidence', {
    method: 'POST',
    body: form,
    headers: { 'Idempotency-Key': draft.localId, 'X-Content-SHA256': draft.sha256 },
  })
}

type SyncOptions = {
  database?: VeriVoteDatabase
  upload?: (draft: EvidenceDraft) => Promise<SubmissionReceipt>
  onConfirmed?: (draft: EvidenceDraft, receipt: SubmissionReceipt) => void
}

let running: Promise<void> | null = null

export function syncEvidence(options: SyncOptions = {}): Promise<void> {
  running ??= run(options).finally(() => {
    running = null
  })
  return running
}

async function run({ database: maybeDatabase, upload = uploadDraft, onConfirmed }: SyncOptions) {
  const database = maybeDatabase ?? (await defaultDatabase())
  // Drafts left in "uploading" by a closed tab are safe to resend: the key is unchanged.
  const pending = (await database.evidenceDrafts.toArray()).filter(
    (draft) =>
      draft.uploadStatus === 'queued' ||
      draft.uploadStatus === 'uploading' ||
      (draft.uploadStatus === 'failed' && !draft.permanentFailure && draft.attempts < MAX_AUTOMATIC_ATTEMPTS),
  )
  if (pending.length === 0) return
  setState({ running: true, total: pending.length, completed: 0, lastError: null })

  let completed = 0
  for (const draft of pending) {
    setState({ currentId: draft.localId })
    await database.evidenceDrafts.update(draft.localId, {
      uploadStatus: 'uploading',
      lastAttemptAt: new Date().toISOString(),
    })
    try {
      const receipt = await upload(draft)
      await database.evidenceDrafts.update(draft.localId, {
        uploadStatus: 'confirmed',
        serverId: receipt.item.id,
        serverReceivedAt: receipt.item.received_at,
        lastError: undefined,
        data: null,
      })
      onConfirmed?.(draft, receipt)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed'
      const transient = isTransient(error)
      const retryLater = transient && draft.attempts + 1 < MAX_AUTOMATIC_ATTEMPTS
      await database.evidenceDrafts.update(draft.localId, {
        uploadStatus: retryLater ? 'queued' : 'failed',
        attempts: draft.attempts + 1,
        lastError: message,
        permanentFailure: !transient,
      })
      setState({ lastError: message })
      // Offline or signed out: stop and wait for the next trigger rather than burning attempts.
      if (error instanceof ApiError && (error.status === 0 || error.status === 401)) break
    }
    completed += 1
    setState({ completed })
  }
  setState({ running: false, currentId: null })
}

/** Uploads queued evidence now and whenever the device reconnects. Returns a cleanup. */
export function startEvidenceSync(onConfirmed?: SyncOptions['onConfirmed']) {
  const sync = () => {
    if (navigator.onLine) void syncEvidence({ onConfirmed }).catch(() => setState({ running: false }))
  }
  window.addEventListener('online', sync)
  sync()
  return () => window.removeEventListener('online', sync)
}
