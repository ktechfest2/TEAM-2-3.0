import Dexie, { type EntityTable } from 'dexie'

/**
 * On-device storage for offline-first workflows. The server remains the source
 * of truth and assigns all verification status. Never store access tokens in
 * IndexedDB, and never cache authenticated (staff) responses here.
 */

export type SyncStatus = 'draft' | 'queued' | 'syncing' | 'synced' | 'failed'

/**
 * An incident report waiting on this device. `id` doubles as the Idempotency-Key, so a
 * resend after a dropped connection returns the original reference. Records saved by
 * earlier versions (notes only, no election or location IDs) stay as `draft` and
 * cannot be submitted; the user re-enters them.
 */
export type IncidentDraft = {
  id: string
  category: string
  description: string
  /** Human-readable place, for the list on this device. */
  locationHint: string
  occurredAt: string
  createdAt: string
  updatedAt: string
  syncStatus: SyncStatus
  electionId?: string
  stateId?: string
  lgaId?: string
  wardId?: string
  pollingUnitId?: string
  timeIsApproximate?: boolean
  latitude?: number
  longitude?: number
  protectIdentity?: boolean
  /** Sent with the account token only if the reporter was signed in when saving. */
  asAccount?: boolean
  photo?: ArrayBuffer | null
  photoName?: string
  photoType?: string
  attempts?: number
  lastError?: string
  permanentFailure?: boolean
  reference?: string
  serverId?: string
  receivedAt?: string
}

export type OutboxEntry = {
  id?: number
  entityType: 'incident_report' | 'evidence_submission' | 'public_refresh'
  /** For public_refresh: the API path to re-fetch. */
  entityId: string
  createdAt: string
  attempts: number
  lastError?: string
}

/** A public, read-only API response saved for offline viewing. */
export type CachedResponse = {
  /** API path including query string, e.g. /polling-units?state_id=… */
  key: string
  payload: unknown
  /** Server `generated_at` of the payload; used to reject stale overwrites. */
  generatedAt: string
  /** When this device last received the payload from the server. */
  syncedAt: string
}

/**
 * A photographed result sheet waiting on this device. The image stays here until the
 * server confirms receipt; `localId` doubles as the upload's idempotency key so
 * retries can never create duplicate submissions.
 */
export type EvidenceUploadStatus = 'queued' | 'uploading' | 'failed' | 'confirmed'

export type EvidenceDraft = {
  localId: string
  electionId: string
  electionName: string
  pollingUnitId: string
  pollingUnitCode: string
  pollingUnitName: string
  fileName: string
  contentType: string
  /** Stored as ArrayBuffer (not Blob) for broad IndexedDB support. Cleared after confirmation. */
  data: ArrayBuffer | null
  byteSize: number
  sha256: string
  captureSource: 'camera' | 'upload'
  /** When the photo was taken or chosen on this device. Separate from server receipt time. */
  capturedAt: string
  createdAt: string
  uploadStatus: EvidenceUploadStatus
  attempts: number
  lastAttemptAt?: string
  lastError?: string
  /** True when the server refused the file; retrying unchanged will not help. */
  permanentFailure?: boolean
  serverId?: string
  serverReceivedAt?: string
}

export class VeriVoteDatabase extends Dexie {
  incidentDrafts!: EntityTable<IncidentDraft, 'id'>
  outbox!: EntityTable<OutboxEntry, 'id'>
  apiCache!: EntityTable<CachedResponse, 'key'>
  evidenceDrafts!: EntityTable<EvidenceDraft, 'localId'>

  constructor(name = 'verivote') {
    super(name)
    this.version(1).stores({
      incidentDrafts: 'id, syncStatus, createdAt',
      outbox: '++id, entityType, entityId, createdAt',
    })
    this.version(2).stores({
      outbox: '++id, entityType, entityId, createdAt, [entityType+entityId]',
      apiCache: 'key, syncedAt',
    })
    this.version(3).stores({
      evidenceDrafts: 'localId, uploadStatus, createdAt',
    })
  }
}

export const db = new VeriVoteDatabase()
