import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  isLegacyDraft,
  listIncidentDrafts,
  queueIncidentReport,
  sendIncidentReport,
  syncIncidentReports,
  type NewIncidentReport,
} from '@/features/public/incidents/drafts'
import { incidentReportSchema } from '@/features/public/incidents/schema'
import type { IncidentReceipt } from '@/features/incidents/types'
import { ApiError, setAccessTokenProvider } from '@/lib/api-client'
import { db, type IncidentDraft } from '@/lib/offline/db'

const recent = new Date(Date.now() - 60 * 60 * 1000).toISOString().slice(0, 16)

const validForm = {
  electionId: 'e1',
  category: 'vote_buying',
  stateId: 's1',
  lgaId: 'l1',
  wardId: '',
  pollingUnitId: '',
  occurredAt: recent,
  timeIsApproximate: true,
  description: 'TEST DATA. Cash was being handed to voters near the queue.',
  latitude: '',
  longitude: '',
  identity: 'anonymous',
} as const

const report: NewIncidentReport = {
  electionId: 'e1',
  category: 'vote_buying',
  description: 'TEST DATA. Cash was being handed to voters near the queue.',
  locationHint: 'DEMO ward',
  stateId: 's1',
  lgaId: 'l1',
  occurredAt: recent,
  timeIsApproximate: true,
  protectIdentity: false,
  asAccount: false,
  photo: { data: new Uint8Array([0xff, 0xd8, 0xff]).buffer, name: 'p.jpg', type: 'image/jpeg' },
}

function receipt(reference = 'VV-TEST-0000-0001'): IncidentReceipt {
  return {
    id: 'server-id',
    reference,
    status: 'received',
    band: 'reported',
    received_at: new Date().toISOString(),
    created: true,
    duplicate: false,
    personal_data_redacted: false,
    attachment_stored: true,
    notice: '',
    privacy_notice: '',
  }
}

describe('incidentReportSchema', () => {
  it('accepts a complete report', () => {
    expect(incidentReportSchema.safeParse(validForm).success).toBe(true)
  })

  it('rejects unknown categories, short text, future times and missing location', () => {
    const result = incidentReportSchema.safeParse({
      ...validForm,
      category: 'made_up',
      description: 'too short',
      occurredAt: '2999-01-01T00:00',
      lgaId: '',
    })
    expect(result.success).toBe(false)
    const fields = result.error?.issues.map((issue) => issue.path[0])
    expect(fields).toEqual(expect.arrayContaining(['category', 'description', 'occurredAt', 'lgaId']))
  })

  it('needs both coordinates or neither, within range', () => {
    expect(incidentReportSchema.safeParse({ ...validForm, latitude: '9.05' }).success).toBe(false)
    expect(incidentReportSchema.safeParse({ ...validForm, latitude: '95', longitude: '7' }).success).toBe(false)
    expect(incidentReportSchema.safeParse({ ...validForm, latitude: '9.05', longitude: '7.49' }).success).toBe(true)
  })
})

describe('offline incident queue', () => {
  beforeEach(async () => {
    await db.incidentDrafts.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
    setAccessTokenProvider(async () => null)
  })

  it('queues locally, sends with the local ID as idempotency key, then forgets the content', async () => {
    const draft = await queueIncidentReport(report, db)
    expect(draft.syncStatus).toBe('queued')
    const send = vi.fn<(draft: IncidentDraft) => Promise<IncidentReceipt>>(async () => receipt())
    await syncIncidentReports({ database: db, send })
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0]?.[0]).toMatchObject({ id: draft.id })
    const [stored] = await listIncidentDrafts(db)
    expect(stored).toMatchObject({ syncStatus: 'synced', reference: 'VV-TEST-0000-0001', description: '', photo: null })
  })

  it('keeps transient failures queued and stops on refused reports', async () => {
    await queueIncidentReport(report, db)
    await syncIncidentReports({ database: db, send: vi.fn(async () => Promise.reject(new ApiError(503, 'down', 'Down'))) })
    expect((await listIncidentDrafts(db))[0]).toMatchObject({ syncStatus: 'queued', attempts: 1 })

    await syncIncidentReports({
      database: db,
      send: vi.fn(async () => Promise.reject(new ApiError(422, 'unknown_lga', 'The LGA is not in that state.'))),
    })
    expect((await listIncidentDrafts(db))[0]).toMatchObject({ syncStatus: 'failed', permanentFailure: true })
  })

  it('never sends drafts saved by the earlier notes-only version', async () => {
    const now = new Date().toISOString()
    await db.incidentDrafts.add({
      id: 'legacy',
      category: 'late_opening',
      description: 'Old note',
      locationHint: 'PU 12',
      occurredAt: now,
      createdAt: now,
      updatedAt: now,
      syncStatus: 'draft',
    })
    const send = vi.fn(async () => receipt())
    await syncIncidentReports({ database: db, send })
    expect(send).not.toHaveBeenCalled()
    expect(isLegacyDraft((await listIncidentDrafts(db))[0]!)).toBe(true)
  })

  it('does not attach a signed-in account to a report saved anonymously', async () => {
    setAccessTokenProvider(async () => 'secret-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify(receipt()), { status: 201, headers: { 'Content-Type': 'application/json' } }),
    )
    const anonymous = await queueIncidentReport(report, db)
    await sendIncidentReport(anonymous)
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBeNull()
    expect(headers.get('Idempotency-Key')).toBe(anonymous.id)
    expect((init.body as FormData).get('protect_identity')).toBe('false')

    const linked = await queueIncidentReport({ ...report, asAccount: true, protectIdentity: true }, db)
    await sendIncidentReport(linked)
    const second = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect(new Headers(second.headers).get('Authorization')).toBe('Bearer secret-token')
    expect((second.body as FormData).get('protect_identity')).toBe('true')
  })
})
