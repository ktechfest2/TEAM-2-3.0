import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { checkEvidenceFile, prepareEvidencePhoto, sha256Hex, sniffType } from '@/features/evidence/file-checks'
import {
  listDrafts,
  resetEvidenceSyncState,
  retryDraft,
  saveDraft,
  syncEvidence,
  type NewDraft,
} from '@/features/evidence/evidence-queue'
import type { EvidenceDetail, Extraction, StatisticalSummary, SubmissionReceipt } from '@/features/evidence/types'
import { ApiError, setAccessTokenProvider } from '@/lib/api-client'
import { VeriVoteDatabase } from '@/lib/offline/db'
import { GENERATED_AT, DEMO_SOURCE, route } from '@/test/mock-api'
import { makeAuthState, renderRoute } from '@/test/render'

/** TEST DATA ONLY: fictional submissions and OCR output, not real election results. */

const JPEG_HEAD = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46, 0x49, 0x46, 0, 1, 1, 0, 0, 1])
const PNG_HEAD = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0x0d, 0x49, 0x48, 0x44, 0x52])

const observer = makeAuthState({ id: 'obs-1', email: 'obs@example.ng', roles: ['observer'] })
const reviewer = makeAuthState({ id: 'rev-1', email: 'rev@example.ng', roles: ['reviewer'] })

let database: VeriVoteDatabase
let counter = 0

beforeEach(() => {
  database = new VeriVoteDatabase(`evidence-test-${++counter}`)
  resetEvidenceSyncState()
})

afterEach(async () => {
  await database.delete()
  vi.unstubAllGlobals()
  setAccessTokenProvider(async () => null)
})

function draftInput(overrides: Partial<NewDraft> = {}): NewDraft {
  return {
    electionId: 'e-1',
    electionName: 'Demo Governorship Election 2026 (fictional)',
    pollingUnitId: 'pu-active',
    pollingUnitCode: 'DEMO-02-01-01-001',
    pollingUnitName: 'Demo Polling Unit A01 (fictional)',
    fileName: 'sheet.jpg',
    contentType: 'image/jpeg',
    data: JPEG_HEAD.buffer.slice(0),
    byteSize: JPEG_HEAD.byteLength,
    sha256: 'a'.repeat(64),
    captureSource: 'camera',
    capturedAt: '2026-11-18T08:30:00.000Z',
    ...overrides,
  }
}

function receipt(id: string): SubmissionReceipt {
  return {
    created: true,
    message: 'Evidence received and fingerprinted.',
    item: { id, received_at: '2026-11-18T09:00:00Z' } as EvidenceDetail,
  }
}

describe('client-side file checks', () => {
  it('identifies formats from content, not the file name', () => {
    expect(sniffType(JPEG_HEAD)).toBe('image/jpeg')
    expect(sniffType(PNG_HEAD)).toBe('image/png')
    expect(sniffType(new TextEncoder().encode('%PDF-1.7 hello'))).toBeNull()
  })

  it('rejects mismatched extensions, unsupported types and oversized files', () => {
    expect(checkEvidenceFile('sheet.jpg', 1000, PNG_HEAD)).toMatchObject({ ok: false })
    expect(checkEvidenceFile('sheet.pdf', 1000, new TextEncoder().encode('%PDF-1.7'))).toMatchObject({ ok: false })
    expect(checkEvidenceFile('sheet.jpg', 16 * 1024 * 1024, JPEG_HEAD)).toMatchObject({ ok: false })
    expect(checkEvidenceFile('sheet.jpeg', 1000, JPEG_HEAD)).toEqual({ ok: true, type: 'image/jpeg' })
  })

  it('keeps a phone photo whose name does not match the bytes', async () => {
    const photo = new File([JPEG_HEAD], 'IMG_2041.HEIC', { type: 'image/heic' })
    const prepared = await prepareEvidencePhoto(photo)
    expect(prepared).toMatchObject({ ok: true, type: 'image/jpeg', fileName: 'IMG_2041.jpg' })
  })

  it('computes SHA-256 of the exact bytes', async () => {
    const digest = await sha256Hex(new TextEncoder().encode('abc').buffer)
    expect(digest).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  })
})

describe('offline evidence queue', () => {
  it('keeps capture time and shows nothing as received until the server confirms', async () => {
    const draft = await saveDraft(draftInput(), database)
    expect(draft.uploadStatus).toBe('queued')
    expect(draft.serverId).toBeUndefined()
    expect(draft.capturedAt).toBe('2026-11-18T08:30:00.000Z')

    const upload = vi.fn(async () => receipt('server-1'))
    await syncEvidence({ database, upload })
    const [stored] = await listDrafts(database)
    expect(stored?.uploadStatus).toBe('confirmed')
    expect(stored?.serverId).toBe('server-1')
    expect(stored?.serverReceivedAt).toBe('2026-11-18T09:00:00Z')
    expect(stored?.capturedAt).toBe('2026-11-18T08:30:00.000Z')
    expect(stored?.data).toBeNull()
  })

  it('sends the draft id as an idempotency key and the client hash', async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () =>
      new Response(JSON.stringify(receipt('server-2')), { status: 201, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const draft = await saveDraft(draftInput(), database)
    await syncEvidence({ database })
    const init = fetchMock.mock.calls[0]?.[1]
    const headers = new Headers(init?.headers)
    expect(headers.get('Idempotency-Key')).toBe(draft.localId)
    expect(headers.get('X-Content-SHA256')).toBe('a'.repeat(64))
    const body = init?.body as FormData
    expect(body.get('captured_at')).toBe('2026-11-18T08:30:00.000Z')
    expect(body.get('polling_unit_id')).toBe('pu-active')
  })

  it('keeps drafts queued when offline and retries with the same key', async () => {
    const draft = await saveDraft(draftInput(), database)
    const keys: string[] = []
    const offline = vi.fn(async (item: { localId: string }) => {
      keys.push(item.localId)
      throw new ApiError(0, 'network_error', 'Unable to reach the VoteTrace server.')
    })
    await syncEvidence({ database, upload: offline })
    let [stored] = await listDrafts(database)
    expect(stored?.uploadStatus).toBe('queued')
    expect(stored?.serverId).toBeUndefined()

    await syncEvidence({ database, upload: async (item) => (keys.push(item.localId), receipt('server-3')) })
    ;[stored] = await listDrafts(database)
    expect(stored?.uploadStatus).toBe('confirmed')
    expect(keys).toEqual([draft.localId, draft.localId])
  })

  it('marks files the server refuses as failed until the user retries', async () => {
    await saveDraft(draftInput(), database)
    const refuse = vi.fn(async () => {
      throw new ApiError(415, 'unsupported_type', 'Only JPEG, PNG and WebP images are accepted.')
    })
    await syncEvidence({ database, upload: refuse })
    await syncEvidence({ database, upload: refuse })
    const [stored] = await listDrafts(database)
    expect(stored?.uploadStatus).toBe('failed')
    expect(stored?.permanentFailure).toBe(true)
    expect(refuse).toHaveBeenCalledTimes(1)

    await retryDraft(stored!.localId, database)
    await syncEvidence({ database, upload: async () => receipt('server-4') })
    expect((await listDrafts(database))[0]?.uploadStatus).toBe('confirmed')
  })
})

const ELECTION = {
  id: 'e-1',
  name: 'Demo Governorship Election 2026 (fictional)',
  election_label: 'GOVERNORSHIP',
  election_date: '2026-12-05',
  template_id: 'generic-pu-result-v1',
  parties: [{ code: 'PA', name: 'Demo Party A (fictional)' }],
  is_demo: true,
}

function detail(overrides: Partial<EvidenceDetail> = {}): EvidenceDetail {
  return {
    id: 'ev-1',
    election: { id: 'e-1', name: ELECTION.name, is_demo: true },
    polling_unit: {
      id: 'pu-active',
      code: 'DEMO-02-01-01-001',
      name: 'Demo Polling Unit A01 (fictional)',
      state: 'Lagos',
      lga: 'Ikeja',
      ward: 'Demo Ward A',
    },
    status: 'flagged_for_review',
    status_changed_at: '2026-11-18T09:05:00Z',
    captured_at: '2026-11-18T08:30:00Z',
    received_at: '2026-11-18T09:00:00Z',
    original_sha256: 'b'.repeat(64),
    is_mine: false,
    submitted_by: 'obs-1',
    template_id: 'generic-pu-result-v1',
    provenance: {},
    processing_error: null,
    images: [],
    allowed_actions: ['correct', 'validate', 'start_review'],
    status_notice: 'VoteTrace statuses describe this platform’s evidence checks and human review. They are not INEC declarations.',
    ...overrides,
  }
}

const EXTRACTION: Extraction = {
  id: 'x-1',
  status: 'completed',
  provider: 'tesseract',
  provider_version: '5.3.0',
  template_id: 'generic-pu-result-v1',
  template_notice: 'Demonstration template. Not a certified INEC form layout.',
  mean_confidence: 0.8,
  confidence_threshold: 0.85,
  error: null,
  raw_text: null,
  processed_image_id: null,
  created_at: '2026-11-18T09:01:00Z',
  attention_fields: ['party:PA'],
  disclaimer: 'OCR output is a draft.',
  fields: [
    {
      field_key: 'party:PA',
      label: 'Demo Party A (fictional)',
      kind: 'integer',
      required: true,
      value: 120,
      origin: 'ocr',
      confidence: 0.31,
      source_text: '12O',
      bbox: null,
      requires_review: true,
      review_reasons: ['ambiguous_characters', 'low_confidence', 'ambiguous:O→0'],
      version: 1,
      ocr_value: 120,
      ocr_confidence: 0.31,
      history: [],
    },
  ],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function installEvidenceApi(item: EvidenceDetail = detail(), statistical: StatisticalSummary | null = null) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://api.test')
    const path = url.pathname.replace(/^.*\/api\/v1/, '')
    if (path === '/elections') return json({ data_source: DEMO_SOURCE, generated_at: GENERATED_AT, items: [ELECTION] })
    if (path === '/evidence' && (init?.method ?? 'GET') === 'GET') {
      return json({ items: [item], page: 1, page_size: 20, total: 1, total_pages: 1, status_notice: item.status_notice })
    }
    if (path === `/evidence/${item.id}`) return json(item)
    if (path === `/evidence/${item.id}/extraction`) return json(EXTRACTION)
    if (path === `/evidence/${item.id}/image`) return json({ error: { code: 'not_found', message: 'No image' } }, 404)
    if (path === `/evidence/${item.id}/anomalies`) {
      return json({
        disclaimer: 'VoteTrace AI flags patterns for human review. It does not determine fraud, reject results or change values.',
        statistical_analysis: statistical,
        alerts: [
          {
            id: 'a-1',
            analysis_run_id: 'run-1',
            category: 'ocr_uncertainty',
            severity: 'high',
            headline: 'Anomaly detected. Human review required.',
            summary: '1 extracted field(s) could not be read with confidence and must be confirmed by a person.',
            fields: ['party:PA'],
            explanation: { why: 'Confidence below the configured threshold.' },
            recommendation: 'A trained reviewer should examine the original image. This alert is not a finding of fraud or wrongdoing.',
            model_name: 'ocr-uncertainty-rules',
            model_version: '1',
            is_demo: false,
            is_current: true,
            created_at: '2026-11-18T09:05:00Z',
          },
        ],
      })
    }
    return route(String(input))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('evidence screens', () => {
  it('requires sign-in for field evidence', async () => {
    installEvidenceApi()
    renderRoute('/evidence/submit')
    expect(await screen.findByLabelText('Password')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Submit a result sheet' })).not.toBeInTheDocument()
  })

  it('lets an observer choose the polling unit and photo', async () => {
    installEvidenceApi()
    renderRoute('/evidence/submit', observer)
    expect(await screen.findByRole('heading', { level: 1, name: 'Submit a result sheet' }, { timeout: 8_000 })).toBeInTheDocument()
    expect(await screen.findByRole('option', { name: ELECTION.name })).toBeInTheDocument()
    expect(screen.getByText('Take photo')).toBeInTheDocument()
    expect(screen.getByLabelText('Take photo with camera')).toHaveAttribute('capture', 'environment')
    expect(screen.getByLabelText('Take photo with camera')).not.toHaveClass('sr-only')
    expect(screen.getAllByText(/not INEC declarations/i).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /save and submit/i }))
    expect(await screen.findByText(/choose the election and polling unit/i)).toBeInTheDocument()
  })

  it('shows uncertain OCR values and AI alerts as needing human review', async () => {
    installEvidenceApi()
    renderRoute('/admin/evidence/ev-1', reviewer)
    expect(await screen.findByRole('heading', { level: 1, name: /DEMO-02-01-01-001/ }, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getAllByText(/not INEC declarations/i).length).toBeGreaterThan(0)
    expect(await screen.findByText('1 field(s) need attention')).toBeInTheDocument()
    expect(screen.getByText('31%')).toBeInTheDocument()
    expect(screen.getByText('Low OCR confidence')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start review/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'AI anomaly report' }))
    const panel = await screen.findByRole('tabpanel')
    expect(await within(panel).findByText('Anomaly detected. Human review required.')).toBeInTheDocument()
    expect(within(panel).getByText(/does not determine fraud/i)).toBeInTheDocument()
    expect(within(panel).queryByText(/fraudulent/i)).not.toBeInTheDocument()
  })

  it('explains a statistical outlier ratio by ratio and keeps it apart from other checks', async () => {
    installEvidenceApi(detail(), {
      status: 'analysed',
      model_name: 'isolation-forest',
      model_version: 'sklearn-1.7/features-v1/empirical-p-v1',
      variables: ['rejected_share', 'turnout_of_accredited'],
      reference_records: 36,
      excluded_reference_records: 0,
      min_samples: 30,
      is_demo: true,
      anomaly_score: '-0.1751',
      empirical_p_value: '0.0270',
      alpha: 0.05,
      is_outlier: true,
      contributing_fields: [
        {
          variable: 'rejected_share',
          description: 'Rejected votes ÷ votes cast',
          value: '0.2400',
          reference_median: '0.0250',
          robust_z: '18.52',
          unusual: true,
        },
        {
          variable: 'turnout_of_accredited',
          description: 'Votes cast ÷ accredited voters',
          value: '0.9950',
          reference_median: '0.9950',
          robust_z: '0.00',
          unusual: false,
        },
      ],
    })
    renderRoute('/admin/evidence/ev-1', reviewer)
    expect(await screen.findByRole('heading', { level: 1, name: /DEMO-02-01-01-001/ }, { timeout: 8_000 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'AI anomaly report' }))
    const section = await screen.findByRole('region', { name: /Statistical analysis/ })
    expect(within(section).getByText('DEMO / SYNTHETIC')).toBeInTheDocument()
    expect(within(section).getByText('Statistical outlier')).toBeInTheDocument()
    expect(within(section).getByText(/p = 0.0270, flagged at p ≤ 0.05/)).toBeInTheDocument()
    expect(within(section).getByText(/Arithmetic checks and differences between submissions are reported separately/)).toBeInTheDocument()
    const rows = within(within(section).getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(within(rows[1]!).getByText('Rejected votes ÷ votes cast')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('18.52 (unusual)')).toBeInTheDocument()
    expect(within(rows[2]!).queryByText(/unusual/)).not.toBeInTheDocument()
    expect(within(section).queryByText(/fraud/i)).not.toBeInTheDocument()
  })

  it('hides staff-only analysis and review controls from submitters', async () => {
    installEvidenceApi(detail({ is_mine: true, submitted_by: null, allowed_actions: ['correct', 'validate'] }))
    renderRoute('/evidence/ev-1', observer)
    expect(await screen.findByRole('heading', { level: 1, name: /DEMO-02-01-01-001/ }, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'AI anomaly report' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Independent comparison' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /validate and cross-check/i })).toBeInTheDocument())
  })

  it('lists the review queue for reviewers', async () => {
    const fetchMock = installEvidenceApi()
    renderRoute('/admin/verification', reviewer)
    expect(await screen.findByRole('heading', { level: 1, name: 'Verification review' }, { timeout: 8_000 })).toBeInTheDocument()
    expect(await screen.findByText(/Demo Polling Unit A01/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('queue=review'))).toBe(true)
  })
})
