import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { IncidentReceipt } from '@/features/incidents/types'
import { ApiError, apiRequest } from '@/lib/api-client'
import type { IncidentDraft, VeriVoteDatabase } from '@/lib/offline/db'
import { defaultDatabase } from '@/lib/offline/public-cache'

/**
 * Offline incident queue. A report is saved on this device first, then sent with its
 * local ID as the Idempotency-Key. It is shown as received only once the server
 * returns a reference. After confirmation the photo and text are removed from the
 * device; only the reference and category are kept.
 */

export const draftKeys = {
  all: ['offline', 'incident-drafts'] as const,
}

export type NewIncidentReport = {
  electionId: string
  category: string
  description: string
  locationHint: string
  stateId: string
  lgaId: string
  wardId?: string
  pollingUnitId?: string
  occurredAt: string
  timeIsApproximate: boolean
  latitude?: number
  longitude?: number
  protectIdentity: boolean
  asAccount: boolean
  photo?: { data: ArrayBuffer; name: string; type: string } | null
}

const MAX_AUTOMATIC_ATTEMPTS = 8

async function target(database?: VeriVoteDatabase) {
  return database ?? (await defaultDatabase())
}

export async function queueIncidentReport(input: NewIncidentReport, database?: VeriVoteDatabase): Promise<IncidentDraft> {
  const now = new Date().toISOString()
  const { photo, ...rest } = input
  const draft: IncidentDraft = {
    ...rest,
    id: crypto.randomUUID(),
    occurredAt: new Date(input.occurredAt).toISOString(),
    photo: photo?.data ?? null,
    photoName: photo?.name,
    photoType: photo?.type,
    createdAt: now,
    updatedAt: now,
    syncStatus: 'queued',
    attempts: 0,
  }
  await (await target(database)).incidentDrafts.add(draft)
  return draft
}

export async function listIncidentDrafts(database?: VeriVoteDatabase) {
  return (await target(database)).incidentDrafts.orderBy('createdAt').reverse().toArray()
}

export async function deleteIncidentDraft(id: string, database?: VeriVoteDatabase) {
  return (await target(database)).incidentDrafts.delete(id)
}

export async function retryIncidentDraft(id: string, database?: VeriVoteDatabase) {
  await (await target(database)).incidentDrafts.update(id, {
    syncStatus: 'queued',
    attempts: 0,
    lastError: undefined,
    permanentFailure: false,
  })
}

/** A record from an earlier version that lacks the fields the server needs. */
export function isLegacyDraft(draft: IncidentDraft) {
  return !draft.electionId || !draft.stateId || !draft.lgaId
}

function isTransient(error: unknown) {
  if (!(error instanceof ApiError)) return true
  return error.status === 0 || error.status === 408 || error.status === 429 || error.status >= 500
}

export async function sendIncidentReport(draft: IncidentDraft): Promise<IncidentReceipt> {
  const form = new FormData()
  form.append('election_id', draft.electionId ?? '')
  form.append('category', draft.category)
  form.append('description', draft.description)
  form.append('state_id', draft.stateId ?? '')
  form.append('lga_id', draft.lgaId ?? '')
  if (draft.wardId) form.append('ward_id', draft.wardId)
  if (draft.pollingUnitId) form.append('polling_unit_id', draft.pollingUnitId)
  form.append('occurred_at', draft.occurredAt)
  form.append('time_is_approximate', String(draft.timeIsApproximate ?? true))
  if (draft.latitude !== undefined && draft.longitude !== undefined) {
    form.append('latitude', String(draft.latitude))
    form.append('longitude', String(draft.longitude))
  }
  form.append('protect_identity', String(Boolean(draft.protectIdentity && draft.asAccount)))
  if (draft.photo && draft.photoType) {
    form.append('file', new Blob([draft.photo], { type: draft.photoType }), draft.photoName ?? 'photo.jpg')
  }
  return apiRequest<IncidentReceipt>('/incidents', {
    method: 'POST',
    body: form,
    headers: { 'Idempotency-Key': draft.id },
    // A report saved without signing in is never linked to an account signed in later.
    auth: Boolean(draft.asAccount),
  })
}

type SyncOptions = {
  database?: VeriVoteDatabase
  send?: (draft: IncidentDraft) => Promise<IncidentReceipt>
  onChange?: () => void
}

let running: Promise<void> | null = null

export function syncIncidentReports(options: SyncOptions = {}): Promise<void> {
  running ??= run(options).finally(() => {
    running = null
  })
  return running
}

async function run({ database: maybeDatabase, send = sendIncidentReport, onChange }: SyncOptions) {
  const database = await target(maybeDatabase)
  const pending = (await database.incidentDrafts.toArray()).filter(
    (draft) =>
      !isLegacyDraft(draft) &&
      (draft.syncStatus === 'queued' ||
        draft.syncStatus === 'syncing' ||
        (draft.syncStatus === 'failed' && !draft.permanentFailure && (draft.attempts ?? 0) < MAX_AUTOMATIC_ATTEMPTS)),
  )
  for (const draft of pending) {
    await database.incidentDrafts.update(draft.id, { syncStatus: 'syncing', updatedAt: new Date().toISOString() })
    onChange?.()
    try {
      const receipt = await send(draft)
      await database.incidentDrafts.update(draft.id, {
        syncStatus: 'synced',
        reference: receipt.reference,
        serverId: receipt.id,
        receivedAt: receipt.received_at,
        description: '',
        photo: null,
        latitude: undefined,
        longitude: undefined,
        lastError: undefined,
        updatedAt: new Date().toISOString(),
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Sending failed'
      const transient = isTransient(error)
      const attempts = (draft.attempts ?? 0) + 1
      await database.incidentDrafts.update(draft.id, {
        syncStatus: transient && attempts < MAX_AUTOMATIC_ATTEMPTS ? 'queued' : 'failed',
        attempts,
        lastError: message,
        permanentFailure: !transient,
        updatedAt: new Date().toISOString(),
      })
      if (error instanceof ApiError && error.status === 0) break
    } finally {
      onChange?.()
    }
  }
}

/** Sends queued reports now and whenever the device reconnects. Returns a cleanup. */
export function startIncidentSync(onChange?: () => void) {
  const sync = () => {
    if (navigator.onLine) void syncIncidentReports({ onChange }).catch(() => undefined)
  }
  window.addEventListener('online', sync)
  sync()
  return () => window.removeEventListener('online', sync)
}

export function useIncidentDrafts() {
  return useQuery({ queryKey: draftKeys.all, queryFn: () => listIncidentDrafts(), networkMode: 'always' })
}

export function useDeleteIncidentDraft() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteIncidentDraft(id),
    networkMode: 'always',
    onSuccess: () => queryClient.invalidateQueries({ queryKey: draftKeys.all }),
  })
}

export function useRetryIncidentDraft() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await retryIncidentDraft(id)
      if (navigator.onLine) await syncIncidentReports()
    },
    networkMode: 'always',
    onSettled: () => queryClient.invalidateQueries({ queryKey: draftKeys.all }),
  })
}
