import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { affectedBy } from '@/features/results/api'
import { DEMO_RESULT_LABEL } from '@/features/results/format'
import { coverageColour } from '@/features/results/map-scale'
import type {
  AreaResponse,
  AreaSummary,
  Coverage,
  PollingUnitPage,
  PollingUnitResultResponse,
  PollingUnitRow,
  StreamTotals,
} from '@/features/results/types'
import { db } from '@/lib/offline/db'
import { DEMO_SOURCE, GENERATED_AT, route } from '@/test/mock-api'
import { makeAuthState, renderRoute } from '@/test/render'

/** TEST DATA ONLY: fictional aggregates in the backend response shape, not election results. */

const ELECTIONS = [
  {
    id: 'e-gov',
    name: 'Demo Governorship Election 2026 (fictional)',
    election_label: 'GOVERNORSHIP',
    election_date: '2026-11-21',
    template_id: 'ec8a',
    parties: [],
    is_demo: true,
  },
  {
    id: 'e-pres',
    name: 'Demo Presidential Election 2027 (fictional)',
    election_label: 'PRESIDENTIAL',
    election_date: '2027-02-20',
    template_id: 'ec8a',
    parties: [],
    is_demo: true,
  },
]
const ELECTION_REF = { id: 'e-pres', name: ELECTIONS[1]!.name, election_label: 'PRESIDENTIAL', is_demo: true }
const NOTICE =
  'VoteTrace is independent civic verification. Figures are not INEC declarations and are not legally binding.'
const PARTIAL = 'Partial results: 16 of 44 expected polling units have not reported.'

function coverage(reporting: number, verified: number, expected: number, extra: Partial<Coverage> = {}): Coverage {
  const pct = (n: number) => Math.round((1000 * n) / expected) / 10
  return {
    expected_polling_units: expected,
    polling_units_with_submissions: reporting + 2,
    reporting_polling_units: reporting,
    verified_polling_units: verified,
    pending_polling_units: reporting + 2 - verified,
    flagged_polling_units: 2,
    conflict_polling_units: 1,
    anomaly_polling_units: 0,
    submission_count: reporting + 6,
    independent_submission_count: reporting + 4,
    rejected_submission_count: 1,
    incomplete_registry_entries: 3,
    reporting_coverage_pct: pct(reporting),
    verification_coverage_pct: pct(verified),
    reporting_label: `${reporting} / ${expected} polling units reporting, ${pct(reporting)}% coverage`,
    verification_label: `${verified} / ${expected} polling units verified, ${pct(verified)}% verification coverage`,
    ...extra,
  }
}

function stream(kind: 'reported' | 'verified', votes: [number, number], included: number): StreamTotals {
  const total = votes[0] + votes[1]
  return {
    stream: kind,
    description: kind === 'reported' ? 'Accepted, agreeing submissions.' : 'Approved by reviewers.',
    polling_units_included: included,
    expected_polling_units: 44,
    registered_voters: 9000,
    accredited_voters: total + 10,
    total_valid_votes: total,
    rejected_votes: 10,
    total_votes_cast: total + 10,
    parties: [
      { code: 'DPA', name: 'Demo Party A', votes: votes[0], share_pct: Math.round((1000 * votes[0]) / total) / 10 },
      { code: 'DPB', name: 'Demo Party B', votes: votes[1], share_pct: Math.round((1000 * votes[1]) / total) / 10 },
    ],
    share_basis: 'party votes in this stream',
  }
}

const lagos: AreaSummary = {
  area: { level: 'state', id: 's-lag', name: 'Lagos', code: 'LA' },
  iso_code: 'NG-LA',
  coverage: coverage(8, 4, 15),
  last_updated_at: GENERATED_AT,
}

const envelope = {
  election: ELECTION_REF,
  data_status: 'demonstration' as const,
  demo_label: DEMO_RESULT_LABEL,
  notice: NOTICE,
  generated_at: GENERATED_AT,
}

const NATIONAL: AreaResponse = {
  ...envelope,
  level: 'national',
  summary: {
    area: { level: 'national', id: null, name: 'Nigeria', code: 'NG' },
    iso_code: null,
    coverage: coverage(28, 14, 44),
    last_updated_at: GENERATED_AT,
  },
  breadcrumbs: [{ level: 'national', id: null, name: 'Nigeria', code: 'NG' }],
  reported: stream('reported', [3100, 2900], 24),
  verified: stream('verified', [1500, 1700], 14),
  child_level: 'state',
  children: [lagos],
  child_areas_reporting: 1,
  child_areas_outstanding: 0,
  alerts: [
    {
      kind: 'unresolved_discrepancies',
      count: 1,
      title: 'Unresolved discrepancies',
      description: 'Conflicting submissions awaiting review.',
      href: '/api/v1/analytics/discrepancies?election_id=e-pres&kind=conflict',
    },
    { kind: 'unusual_patterns', count: 0, title: 'Unusual patterns', description: '', href: null },
  ],
  partial_notice: PARTIAL,
  provenance: {
    aggregation_level: 'national',
    registry_source: DEMO_SOURCE,
    method: 'Sum of per-polling-unit results.',
    source_records_path: '/api/v1/analytics/polling-units?election_id=e-pres',
  },
}

const UNIT: PollingUnitRow = {
  id: 'pu-1',
  code: 'DEMO-02-01-01-001',
  name: 'Demo Polling Unit A01 (fictional)',
  ward: { level: 'ward', id: 'w-a', name: 'Demo Ward A', code: '01' },
  lga: { level: 'lga', id: 'l-ikj', name: 'Ikeja', code: '01' },
  state: { level: 'state', id: 's-lag', name: 'Lagos', code: 'LA' },
  status: 'conflict',
  submission_count: 2,
  accepted_count: 2,
  independent_count: 2,
  distinct_results: 2,
  has_flagged: true,
  has_anomaly: false,
  reported_result_hash: null,
  verified_result_hash: null,
  registry_incomplete: true,
  revision: 3,
  updated_at: GENERATED_AT,
}

const UNIT_RESULT: PollingUnitResultResponse = {
  ...envelope,
  unit: UNIT,
  breadcrumbs: [NATIONAL.breadcrumbs[0]!, UNIT.state, UNIT.lga, UNIT.ward, { ...UNIT, level: 'polling_unit' }],
  reported: stream('reported', [0, 0], 0),
  verified: stream('verified', [0, 0], 0),
  verification: {
    status: 'conflict',
    required_approvals: 2,
    approvals_on_verified_result: 0,
    verified_at: null,
    checks_passed: 6,
    checks_failed: 0,
    warnings: 0,
    disclaimer: 'Independent civic verification; not an INEC declaration.',
  },
  source_records: [
    {
      submission_id: 'sub-11111111',
      workflow_status: 'CROSS_CHECKED',
      received_at: GENERATED_AT,
      result_fingerprint: 'abcdef0123456789',
      validation_passed: true,
      agrees_with_reported: null,
      contributes: false,
    },
  ],
}

function unitPage(items: PollingUnitRow[]): PollingUnitPage {
  return { ...envelope, items, page: 1, page_size: 50, total: items.length, total_pages: 1 }
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function analyticsRoute(input: string): Response {
  const url = new URL(input, 'http://api.test')
  const path = url.pathname.replace(/^\/api\/v1/, '')
  if (path === '/elections') return json({ generated_at: GENERATED_AT, items: ELECTIONS })
  if (path === '/analytics/national') return json(NATIONAL)
  if (path === '/analytics/party-results')
    return json({
      ...envelope,
      area: NATIONAL.summary.area,
      reported: NATIONAL.reported,
      verified: NATIONAL.verified,
      breakdown_level: 'state',
      breakdown: [{ area: lagos.area, reported: NATIONAL.reported, verified: NATIONAL.verified }],
      partial_notice: PARTIAL,
    })
  if (path === '/analytics/progress')
    return json({
      ...envelope,
      area: NATIONAL.summary.area,
      expected_polling_units: 44,
      bucket: 'hour',
      points: [
        { at: '2026-11-18T08:00:00Z', reporting_polling_units: 10, verified_polling_units: 2 },
        { at: '2026-11-18T09:00:00Z', reporting_polling_units: 28, verified_polling_units: 14 },
      ],
      description: 'Cumulative polling units by hour.',
    })
  if (path === '/analytics/polling-units/pu-1') return json(UNIT_RESULT)
  if (path === '/analytics/discrepancies' || path === '/analytics/polling-units') return json(unitPage([UNIT]))
  if (path.startsWith('/analytics/')) return json({ error: { code: 'not_found' } }, 404)
  if (path.startsWith('/geo/')) return new Response('missing', { status: 404 })
  return route(input)
}

function installAnalyticsApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => analyticsRoute(String(input)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const calledWith = (mock: ReturnType<typeof installAnalyticsApi>, fragment: string) =>
  mock.mock.calls.some(([input]) => String(input).includes(fragment))

beforeEach(async () => {
  await db.apiCache.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('national results dashboard', () => {
  it('keeps reporting and verification coverage separate', async () => {
    installAnalyticsApi()
    renderRoute('/results')
    expect(await screen.findByText('28 / 44 polling units reporting, 63.6% coverage', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getByText('14 / 44 polling units verified, 31.8% verification coverage')).toBeInTheDocument()
    expect(screen.getByText('Unique polling units reporting')).toBeInTheDocument()
    expect(screen.getByText('Submissions received')).toBeInTheDocument()
    expect(screen.queryByText(DEMO_RESULT_LABEL)).not.toBeInTheDocument()
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument()
    expect(screen.queryByText(PARTIAL)).not.toBeInTheDocument()
  })

  it('defaults to the national-scope election', async () => {
    const fetchMock = installAnalyticsApi()
    renderRoute('/results')
    await screen.findByText('Unique polling units reporting', {}, { timeout: 8_000 })
    expect(calledWith(fetchMock, '/analytics/national?election_id=e-pres')).toBe(true)
  })

  it('shows reported and verified party figures side by side with labelled shares and no winner', async () => {
    installAnalyticsApi()
    renderRoute('/results')
    const table = await screen.findByRole('table', { name: 'Reported and verified votes per party' }, { timeout: 8_000 })
    const row = within(table).getByRole('row', { name: /DPA/ })
    expect(row).toHaveTextContent('3,100')
    expect(row).toHaveTextContent('51.7%')
    expect(row).toHaveTextContent('1,500')
    expect(row).toHaveTextContent('46.9%')
    expect(screen.getByText(/share of party votes/)).toBeInTheDocument()
    expect(screen.getByRole('main')).not.toHaveTextContent(/winner|\bwon\b|\bwins\b|leading|\bleads\b|declared/i)
  })

  it('drills down to states and links alerts to source records', async () => {
    installAnalyticsApi()
    renderRoute('/results')
    const state = await screen.findByRole('link', { name: 'Lagos' }, { timeout: 8_000 })
    expect(state).toHaveAttribute('href', '/results/states/s-lag?election=e-pres')
    expect(screen.getByRole('link', { name: /Unresolved discrepancies/ })).toHaveAttribute(
      'href',
      '/results/records?election=e-pres&kind=conflict',
    )
    expect(screen.getByRole('link', { name: /polling units with submissions/ })).toHaveAttribute(
      'href',
      '/results/records?election=e-pres',
    )
  })

  it('states when figures last changed, and falls back when the map cannot load', async () => {
    installAnalyticsApi()
    renderRoute('/results')
    expect(await screen.findByText(/Last result change/, {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(
      await screen.findByText('State boundaries could not be loaded. Use the state table instead.', {}, { timeout: 8_000 }),
    ).toBeInTheDocument()
  })

  it('never presents a saved copy as live data', async () => {
    installAnalyticsApi()
    const first = renderRoute('/results')
    await screen.findByText('Unique polling units reporting', {}, { timeout: 8_000 })
    first.unmount()
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    renderRoute('/results')
    expect(await screen.findByText('Saved copy. This is not live data', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.queryByText('Live updates on')).not.toBeInTheDocument()
  })
})

describe('polling unit result', () => {
  it('shows the public verification report without submitter details or evidence links', async () => {
    installAnalyticsApi()
    renderRoute('/results/polling-units/pu-1?election=e-pres')
    expect(await screen.findByText('Public verification report', {}, { timeout: 8_000 })).toBeInTheDocument()
    expect(screen.getAllByText('Conflicting submissions').length).toBeGreaterThan(0)
    expect(screen.getByText('Incomplete location record')).toBeInTheDocument()
    expect(screen.getByText('sub-1111')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'sub-1111' })).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(/submitted_by|storage_key|@example/)
  })

  it('gives staff a link into the evidence review workspace', async () => {
    installAnalyticsApi()
    renderRoute(
      '/results/polling-units/pu-1?election=e-pres',
      makeAuthState({ id: 'rev-1', email: 'rev@example.ng', roles: ['reviewer'] }),
    )
    const link = await screen.findByRole('link', { name: 'sub-1111' }, { timeout: 8_000 })
    expect(link).toHaveAttribute('href', '/admin/evidence/sub-11111111')
  })
})

describe('source records', () => {
  it('requests the discrepancy list for a scope and ignores unknown filters', async () => {
    const fetchMock = installAnalyticsApi()
    renderRoute('/results/records?election=e-pres&state_id=0b0e7a52-8d4e-4b69-9a3a-1f2d3c4b5a69&kind=conflict')
    expect(await screen.findByText('Polling units with conflicting submissions', {}, { timeout: 8_000 })).toBeInTheDocument()
    await screen.findByRole('link', { name: UNIT.name })
    expect(
      calledWith(fetchMock, '/analytics/discrepancies?election_id=e-pres&kind=conflict&page=1&state_id=0b0e7a52'),
    ).toBe(true)

    fetchMock.mockClear()
    renderRoute('/results/records?election=e-pres&state_id=not-a-uuid&kind=drop-table')
    expect(await screen.findByText('Polling units behind these totals', {}, { timeout: 8_000 })).toBeInTheDocument()
    await waitFor(() => expect(calledWith(fetchMock, '/analytics/polling-units?election_id=e-pres&page=1')).toBe(true))
    expect(calledWith(fetchMock, 'not-a-uuid')).toBe(false)
  })
})

describe('live update targeting', () => {
  const change = { election_id: 'e-pres', polling_unit_id: 'pu-1', ward_id: 'w-a', lga_id: 'l-ikj', state_id: 's-lag' }

  it('refetches only views that contain the changed polling unit', () => {
    expect(affectedBy('/national?election_id=e-pres', change)).toBe(true)
    expect(affectedBy('/states/s-lag?election_id=e-pres', change)).toBe(true)
    expect(affectedBy('/states/s-fct?election_id=e-pres', change)).toBe(false)
    expect(affectedBy('/wards/w-b?election_id=e-pres', change)).toBe(false)
    expect(affectedBy('/national?election_id=e-gov', change)).toBe(false)
  })

  it('colours the map by coverage only', () => {
    expect(coverageColour(null)).toBe(coverageColour(0))
    expect(coverageColour(80)).not.toBe(coverageColour(30))
  })
})
