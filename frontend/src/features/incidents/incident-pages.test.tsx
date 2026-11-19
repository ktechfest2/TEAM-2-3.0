import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  IncidentDetail,
  IncidentReceipt,
  IncidentStats,
  IncidentSummary,
  PublicIncidentSummary,
} from '@/features/incidents/types'
import { setAccessTokenProvider } from '@/lib/api-client'
import { db } from '@/lib/offline/db'
import { DEMO_SOURCE, GENERATED_AT, route } from '@/test/mock-api'
import { makeAuthState, renderRoute } from '@/test/render'

/** TEST DATA. Fictional elections, places and reports in the backend response shape. */

const ELECTION = {
  id: 'e-pres',
  name: 'Demo Presidential Election (fictional)',
  election_label: 'PRESIDENTIAL',
  election_date: '2026-11-21',
  template_id: 'demo',
  parties: [],
  is_demo: true,
}

const SUMMARY: IncidentSummary = {
  id: 'i-1',
  reference: 'VV-TEST-AAAA-0001',
  election_id: 'e-pres',
  category: 'vote_buying',
  reported_category: 'vote_buying',
  severity: 'medium',
  status: 'received',
  band: 'reported',
  state: { id: 's-lag', name: 'Lagos' },
  lga: { id: 'l-ikj', name: 'Ikeja' },
  ward: { id: 'w-a', name: 'Demo Ward A' },
  polling_unit: { id: 'pu-active', name: 'Demo Polling Unit A01 (fictional)', code: 'DEMO-02-01-01-001' },
  occurred_at: '2026-11-18T09:00:00Z',
  time_is_approximate: true,
  received_at: '2026-11-18T09:10:00Z',
  status_changed_at: '2026-11-18T09:10:00Z',
  excerpt: 'TEST DATA. Cash handed to voters.',
  has_attachment: false,
  possible_duplicate_of: 'VV-TEST-AAAA-0000',
  similar_count: 1,
  missing_count: 2,
  reporter: 'anonymous',
  is_public: false,
}

const DETAIL: IncidentDetail = {
  ...SUMMARY,
  description: 'TEST DATA. Cash handed to voters in the queue near the entrance.',
  latitude: null,
  longitude: null,
  triage: {
    classification: {
      suggested_category: 'vote_buying',
      agrees_with_reporter: true,
      matched_keywords: { vote_buying: ['cash'] },
      note: 'Keyword suggestion only.',
    },
    severity: { level: 'medium', reasons: ['Base level for this category: medium.'] },
    missing_information: [{ field: 'image', message: 'No supporting image.' }],
    similar_reports: [{ id: 'i-0', reference: 'VV-TEST-AAAA-0000', similarity: 0.8, same_polling_unit: true }],
    corroborating_reports: 1,
  },
  attachments: [],
  reviews: [],
  public_summary: null,
  published_at: null,
  resolution_basis: null,
  reporter_user_id: null,
  allowed_transitions: ['screening', 'rejected'],
  can_review: true,
  channel: 'web',
}

const STATS: IncidentStats = {
  total: 3,
  awaiting_review: 2,
  under_investigation: 0,
  verified: 1,
  unverified: 0,
  inconclusive: 0,
  rejected: 0,
  resolved: 0,
  possible_duplicates: 1,
  critical_open: 0,
  by_category: [{ key: 'vote_buying', label: 'Vote-buying allegation', count: 3 }],
  by_status: [],
  by_severity: [],
  by_band: [{ key: 'reported', label: 'Reported', count: 2 }],
  by_state: [{ id: 's-lag', name: 'Lagos', parent: null, count: 3 }],
  by_lga: [{ id: 'l-ikj', name: 'Ikeja', parent: 'Lagos', count: 3 }],
  timeline_bucket: 'hour',
  timeline: [{ period: '2026-11-18T09:00:00Z', count: 3 }],
  notice: 'Reports are allegations.',
  generated_at: GENERATED_AT,
}

const PUBLIC: PublicIncidentSummary = {
  election_id: 'e-pres',
  by_band: [
    { key: 'reported', label: 'Reported', count: 2 },
    { key: 'verified', label: 'Verified', count: 1 },
  ],
  published: [
    {
      category: 'intimidation',
      state: 'Lagos',
      lga: 'Ikeja',
      occurred_on: '2026-11-18',
      summary: 'Reviewers verified reports of voter intimidation at a demo polling unit.',
      published_at: '2026-11-18T12:00:00Z',
    },
  ],
  notice: 'Reports are allegations.',
  demo_label: 'Sample data. Not an official election result.',
  generated_at: GENERATED_AT,
}

const RECEIPT: IncidentReceipt = {
  id: 'i-new',
  reference: 'VV-TEST-NEW0-0001',
  status: 'received',
  band: 'reported',
  received_at: '2026-11-18T10:00:00Z',
  created: true,
  duplicate: false,
  personal_data_redacted: false,
  attachment_stored: false,
  notice: '',
  privacy_notice: '',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

type Call = { url: string; method: string; headers: Headers; body: unknown }

function installApi({ canReview = true } = {}) {
  const calls: Call[] = []
  let detail: IncidentDetail = canReview ? DETAIL : { ...DETAIL, can_review: false, allowed_transitions: [] }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://api.test')
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const method = init?.method ?? 'GET'
    calls.push({ url: path + url.search, method, headers: new Headers(init?.headers), body: init?.body })
    if (path === '/elections') return json({ data_source: DEMO_SOURCE, generated_at: GENERATED_AT, items: [ELECTION] })
    if (path === '/incidents' && method === 'POST') return json(RECEIPT, 201)
    if (path.startsWith('/incidents/track/')) {
      return path.endsWith('VV-TEST-AAAA-0001')
        ? json({ reference: 'VV-TEST-AAAA-0001', band: 'under_review', band_label: 'Under review', received_at: GENERATED_AT, last_updated_at: GENERATED_AT, public_summary: null, notice: '' })
        : json({ error: { code: 'not_found', message: 'No report has that reference.' } }, 404)
    }
    if (path === '/incidents/stats') return json(STATS)
    if (path === '/incidents') {
      return json({ items: [SUMMARY], page: 1, page_size: 25, total: 1, total_pages: 1, notice: '', generated_at: GENERATED_AT })
    }
    if (path === '/incidents/i-1/review') {
      const payload = JSON.parse(String(init?.body))
      detail = {
        ...detail,
        status: payload.new_status,
        status_changed_at: '2026-11-18T11:00:00Z',
        allowed_transitions: ['under_review'],
        reviews: [
          {
            id: 'r-1',
            reviewer_id: 'rev-1',
            previous_status: 'received',
            new_status: payload.new_status,
            reason: payload.reason,
            evidence_refs: payload.evidence_refs,
            category_from: null,
            category_to: null,
            severity_from: null,
            severity_to: null,
            public_summary: null,
            published: false,
            created_at: '2026-11-18T11:00:00Z',
          },
        ],
      }
      return json(detail)
    }
    if (path === '/incidents/i-1') return json(detail)
    if (path === '/public/incidents') return json(PUBLIC)
    if (path === '/ussd/sessions') {
      return json({ session_id: 's1', text: 'Welcome to VoteTrace\n1. Polling Unit Results', end: false, timed_out: false, timeout_seconds: 180, election: ELECTION.name, demo_label: 'DEMO', notice: '' }, 201)
    }
    if (path === '/ussd/sessions/s1/input') {
      return json({ session_id: 's1', text: 'Nigeria\nExpected PUs: 13\n0. Main menu', end: false, timed_out: false, timeout_seconds: 180, election: ELECTION.name, demo_label: 'DEMO', notice: '' })
    }
    if (path === '/sms/incoming') {
      return json({ message_ref: 'SMS-TEST000001', command: 'HELP', outcome: 'ok', parts: ['(1/1) VoteTrace commands: RESULT <PU code>'], has_more: false, duplicate: false, provider: 'simulator', notice: '' })
    }
    return route(String(input))
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

const reviewer = makeAuthState({ id: 'rev-1', email: 'rev@example.ng', roles: ['reviewer'] })
const auditor = makeAuthState({ id: 'aud-1', email: 'aud@example.ng', roles: ['auditor'] })

beforeEach(async () => {
  await db.incidentDrafts.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessTokenProvider(async () => null)
})

describe('report an incident', () => {
  it('validates required fields before sending', async () => {
    const calls = installApi()
    const user = userEvent.setup()
    renderRoute('/report-incident')
    await user.click(await screen.findByRole('button', { name: 'Send report' }))
    expect(await screen.findByText('Select a category', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('Choose the state')).toBeInTheDocument()
    expect(screen.getByText('Describe what happened in at least 20 characters')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('sends an anonymous report and shows the reference', async () => {
    const calls = installApi()
    setAccessTokenProvider(async () => 'should-not-be-sent')
    const user = userEvent.setup()
    renderRoute('/report-incident')
    await waitFor(() => expect(screen.getByLabelText(/Election/)).toHaveValue('e-pres'))
    await user.selectOptions(screen.getByLabelText(/Category/), 'vote_buying')
    await user.selectOptions(await screen.findByLabelText(/^State/), 's-lag')
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ikeja' })).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/Local Government Area/), 'l-ikj')
    await user.type(screen.getByLabelText(/What happened/), 'TEST DATA. Cash was handed to voters near the queue.')
    await user.click(screen.getByRole('button', { name: 'Send report' }))

    expect(await screen.findByTestId('incident-reference')).toHaveTextContent('VV-TEST-NEW0-0001')
    const post = calls.find((call) => call.method === 'POST' && call.url === '/incidents')!
    expect(post.headers.get('Authorization')).toBeNull()
    expect(post.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
    const form = post.body as FormData
    expect(form.get('category')).toBe('vote_buying')
    expect(form.get('lga_id')).toBe('l-ikj')
    expect(form.get('protect_identity')).toBe('false')
    const [stored] = await db.incidentDrafts.toArray()
    expect(stored).toMatchObject({ syncStatus: 'synced', description: '' })
  })

  it('offers protected reporting only to signed-in users', async () => {
    installApi()
    renderRoute('/report-incident', makeAuthState({ id: 'obs-1', email: 'o@example.ng', roles: ['observer'] }))
    expect(await screen.findByLabelText(/Protected/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Send without my account/)).toBeChecked()
  })

  it('tracks a report by reference without showing its content', async () => {
    installApi()
    const user = userEvent.setup()
    renderRoute('/report-incident')
    await user.type(await screen.findByLabelText('Reference number'), 'vv-test-aaaa-0001')
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText('Reviewers are checking the report.')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Reference number'))
    await user.type(screen.getByLabelText('Reference number'), 'VV-NOPE-NOPE-NOPE')
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText(/No report has that reference/)).toBeInTheDocument()
  })
})

describe('incident review area', () => {
  it('shows totals, breakdowns and the queue with duplicate indicators', async () => {
    installApi()
    renderRoute('/admin/incidents', reviewer)
    expect(await screen.findByRole('heading', { level: 1, name: 'Incidents' })).toBeInTheDocument()
    const totals = await screen.findByRole('region', { name: 'Totals' })
    expect(within(totals).getByText('Total reports')).toBeInTheDocument()
    expect(within(totals).getByText('Awaiting review')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'VV-TEST-AAAA-0001' })).toHaveAttribute('href', '/admin/incidents/i-1')
    expect(screen.getByText('Possible duplicate')).toBeInTheDocument()
  })

  it('lets a reviewer move a report on with a recorded reason', async () => {
    const calls = installApi()
    const user = userEvent.setup()
    renderRoute('/admin/incidents/i-1', reviewer)
    expect(await screen.findByRole('heading', { level: 1, name: 'VV-TEST-AAAA-0001' })).toBeInTheDocument()
    expect(screen.getByText(/Possible duplicate of VV-TEST-AAAA-0000/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(/New status/), 'screening')
    await user.type(screen.getByLabelText(/^Reason/), 'Initial screening of the report.')
    await user.click(screen.getByRole('button', { name: 'Save review' }))
    await waitFor(() => expect(calls.some((call) => call.url === '/incidents/i-1/review')).toBe(true))
    const review = calls.find((call) => call.url === '/incidents/i-1/review')!
    expect(JSON.parse(String(review.body))).toMatchObject({ new_status: 'screening', reason: 'Initial screening of the report.' })
    expect(await screen.findByText('Initial screening of the report.')).toBeInTheDocument()
  })

  it('offers only the transitions the server allows', async () => {
    installApi()
    renderRoute('/admin/incidents/i-1', reviewer)
    await screen.findByRole('heading', { level: 1, name: 'VV-TEST-AAAA-0001' })
    const status = screen.getByLabelText(/New status/) as HTMLSelectElement
    expect(Array.from(status.options).map((option) => option.value)).not.toContain('verified')
  })

  it('is read-only for auditors', async () => {
    installApi({ canReview: false })
    renderRoute('/admin/incidents/i-1', auditor)
    expect(await screen.findByText(/Read only/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save review' })).not.toBeInTheDocument()
  })
})

describe('public incident summary and phone access', () => {
  it('shows stage counts and reviewer-approved summaries only', async () => {
    installApi()
    renderRoute('/incidents')
    expect(await screen.findByText(PUBLIC.published[0]!.summary)).toBeInTheDocument()
    expect(screen.getByText('Reports by review stage')).toBeInTheDocument()
    expect(screen.queryByText(/VV-TEST/)).not.toBeInTheDocument()
  })

  it('runs the USSD and SMS simulators against the API', async () => {
    const calls = installApi()
    const user = userEvent.setup()
    renderRoute('/phone-access')
    expect(await screen.findByText('Test console')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Dial' }))
    expect(await screen.findByTestId('ussd-screen')).toHaveTextContent('Welcome to VoteTrace')
    await user.type(screen.getByLabelText('USSD reply'), '5')
    await user.click(screen.getAllByRole('button', { name: 'Send' })[0]!)
    expect(await screen.findByTestId('ussd-screen')).toHaveTextContent('Expected PUs: 13')

    await user.click(screen.getByRole('button', { name: 'HELP' }))
    expect(await screen.findByText(/VoteTrace commands/)).toBeInTheDocument()
    expect(screen.getByText('SMS-TEST000001')).toBeInTheDocument()
    expect(calls.find((call) => call.url === '/sms/incoming')!.headers.get('Authorization')).toBeNull()
  })
})
