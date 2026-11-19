import { vi } from 'vitest'
import type {
  DataSource,
  ElectionUpdate,
  Lga,
  PollingUnitDetail,
  PollingUnitSummary,
  State,
  Ward,
} from '@/features/directory/types'

/** Fixtures in the backend response shape. Fictional, like the backend demo dataset. */

export const DEMO_SOURCE: DataSource = {
  kind: 'demo',
  label: 'Sample data',
  description: 'Fictional demonstration data. Not sourced from INEC.',
}

export const GENERATED_AT = '2026-11-18T10:00:00Z'

export const STATES: State[] = [
  { id: 's-fct', code: 'FC', name: 'Federal Capital Territory' },
  { id: 's-lag', code: 'LA', name: 'Lagos' },
]
export const LGAS: Lga[] = [
  { id: 'l-ikj', state_id: 's-lag', code: '01', name: 'Ikeja' },
  { id: 'l-amac', state_id: 's-fct', code: '01', name: 'Abuja Municipal' },
]
export const WARDS: Ward[] = [{ id: 'w-a', lga_id: 'l-ikj', code: '01', name: 'Demo Ward A' }]

const where = {
  state: { id: 's-lag', name: 'Lagos' },
  lga: { id: 'l-ikj', name: 'Ikeja' },
  ward: { id: 'w-a', name: 'Demo Ward A' },
}

const base = {
  ...where,
  source_name: 'VoteTrace demonstration dataset (not INEC)',
  source_updated_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-01T09:00:00Z',
  official_notices: [],
  relocation_reports: null,
}

export const POLLING_UNITS: PollingUnitDetail[] = [
  {
    ...base,
    id: 'pu-active',
    code: 'DEMO-02-01-01-001',
    name: 'Demo Polling Unit A01 (fictional)',
    address_description: 'Fictional address for demonstration',
    coordinates: { latitude: 6.6, longitude: 3.35, precision: 'demo_approximate' },
    status: 'active',
  },
  {
    ...base,
    id: 'pu-official',
    code: 'DEMO-02-01-01-002',
    name: 'Demo Polling Unit A02 (fictional)',
    address_description: null,
    coordinates: null,
    status: 'officially_relocated',
    official_notices: [
      {
        id: 'n-1',
        kind: 'relocation',
        source_name: 'Demonstration notice (not an INEC announcement)',
        source_url: null,
        reference: 'DEMO-REF-0001',
        new_location_description: 'Fictional new location',
        effective_date: '2026-11-20',
        received_at: '2026-11-10T12:00:00Z',
        verification_status: 'officially_confirmed',
      },
    ],
  },
  {
    ...base,
    id: 'pu-reported',
    code: 'DEMO-02-01-01-003',
    name: 'Demo Polling Unit A03 (fictional)',
    address_description: null,
    coordinates: null,
    status: 'relocation_reported',
    relocation_reports: {
      report_count: 3,
      first_reported_at: '2026-11-12T08:00:00Z',
      last_reported_at: '2026-11-13T08:00:00Z',
    },
  },
  {
    ...base,
    id: 'pu-closed',
    code: 'DEMO-02-01-01-004',
    name: 'Demo Polling Unit A04 (fictional)',
    address_description: null,
    coordinates: null,
    status: 'temporarily_unavailable',
    official_notices: [
      {
        id: 'n-2',
        kind: 'temporary_closure',
        source_name: null,
        source_url: null,
        reference: null,
        new_location_description: null,
        effective_date: null,
        received_at: '2026-11-11T12:00:00Z',
        verification_status: 'awaiting_confirmation',
      },
    ],
  },
]

export const UPDATES: ElectionUpdate[] = [
  {
    id: 'u-official',
    title: 'Demo: polling unit relocation confirmed',
    description: 'Fictional confirmed relocation for demonstration.',
    category: 'polling_unit_relocation',
    source_name: 'Demonstration notice (not an INEC announcement)',
    source_url: null,
    reference: 'DEMO-REF-0001',
    verification_status: 'officially_confirmed',
    polling_unit_id: 'pu-official',
    published_at: '2026-11-14T09:00:00Z',
    is_demo: true,
  },
  {
    id: 'u-verified',
    title: 'Demo: voting delay checked by observers',
    description: 'Fictional delay report checked independently.',
    category: 'voting_delay',
    source_name: 'VoteTrace demonstration team',
    source_url: null,
    reference: null,
    verification_status: 'independently_verified',
    polling_unit_id: null,
    published_at: '2026-11-12T09:00:00Z',
    is_demo: true,
  },
  {
    id: 'u-reported',
    title: 'Demo: unconfirmed relocation report',
    description: 'Fictional report that has not been verified.',
    category: 'polling_unit_relocation',
    source_name: 'Public report (demonstration)',
    source_url: null,
    reference: null,
    verification_status: 'reported_unverified',
    polling_unit_id: 'pu-reported',
    published_at: '2026-11-10T09:00:00Z',
    is_demo: true,
  },
]

const envelope = () => ({ data_source: DEMO_SOURCE, generated_at: GENERATED_AT })

function page<T>(items: T[], params: URLSearchParams) {
  const pageNumber = Number(params.get('page') ?? 1)
  const size = Number(params.get('page_size') ?? 20)
  return {
    ...envelope(),
    items: items.slice((pageNumber - 1) * size, pageNumber * size),
    page: pageNumber,
    page_size: size,
    total: items.length,
    total_pages: Math.max(1, Math.ceil(items.length / size)),
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function notFound() {
  return json({ error: { code: 'not_found', message: 'Not found.', request_id: 'test' } }, 404)
}

function summary(unit: PollingUnitDetail): PollingUnitSummary {
  return {
    id: unit.id,
    code: unit.code,
    name: unit.name,
    state: unit.state,
    lga: unit.lga,
    ward: unit.ward,
    address_description: unit.address_description,
    coordinates: unit.coordinates,
    status: unit.status,
    source_name: unit.source_name,
    source_updated_at: unit.source_updated_at,
    updated_at: unit.updated_at,
  }
}

export function route(path: string): Response {
  const url = new URL(path, 'http://api.test')
  const p = url.searchParams
  const segments = url.pathname.replace(/^\/api\/v1/, '').split('/').filter(Boolean)
  const [resource, id] = segments

  if (url.pathname.endsWith('/locations/states')) return json({ ...envelope(), items: STATES })
  if (url.pathname.endsWith('/locations/lgas'))
    return json({ ...envelope(), items: LGAS.filter((l) => l.state_id === p.get('state_id')) })
  if (url.pathname.endsWith('/locations/wards'))
    return json({ ...envelope(), items: WARDS.filter((w) => w.lga_id === p.get('lga_id')) })

  if (resource === 'polling-units' && id) {
    const unit = POLLING_UNITS.find((u) => u.id === id)
    return unit ? json({ ...envelope(), item: unit }) : notFound()
  }
  if (resource === 'polling-units') {
    const q = p.get('q')?.toLowerCase()
    const items = POLLING_UNITS.filter(
      (u) =>
        (!p.get('state_id') || u.state.id === p.get('state_id')) &&
        (!p.get('lga_id') || u.lga.id === p.get('lga_id')) &&
        (!p.get('ward_id') || u.ward.id === p.get('ward_id')) &&
        (!q || `${u.name} ${u.code}`.toLowerCase().includes(q)),
    ).map(summary)
    return json(page(items, p))
  }

  if (resource === 'updates' && id) {
    const update = UPDATES.find((u) => u.id === id)
    return update ? json({ ...envelope(), item: update }) : notFound()
  }
  if (resource === 'updates') {
    const items = UPDATES.filter(
      (u) =>
        (!p.get('category') || u.category === p.get('category')) &&
        (!p.get('verification_status') || u.verification_status === p.get('verification_status')),
    )
    return json(page(items, p))
  }
  return notFound()
}

/** Replaces global fetch with the fixture API. Returns the mock for request assertions. */
export function installMockApi() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async (input) =>
    route(String(input)),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function installOfflineApi() {
  const fetchMock = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
