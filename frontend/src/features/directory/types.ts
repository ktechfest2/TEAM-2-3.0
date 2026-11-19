/** Mirrors backend/app/schemas (common, locations, polling_units, updates). */

export type DataSource = {
  kind: 'demo' | 'official'
  label: string
  description: string
}

type Envelope = { data_source: DataSource; generated_at: string }

export type ListResponse<T> = Envelope & { items: T[] }
export type PageResponse<T> = ListResponse<T> & {
  page: number
  page_size: number
  total: number
  total_pages: number
}
export type ItemResponse<T> = Envelope & { item: T }

export type LocationRef = { id: string; name: string }
export type State = { id: string; code: string; name: string; iso_code?: string | null }
export type Lga = { id: string; state_id: string; code: string; name: string }
export type Ward = { id: string; lga_id: string; code: string; name: string }

export const POLLING_UNIT_STATUSES = [
  'active',
  'relocation_reported',
  'officially_relocated',
  'temporarily_unavailable',
  'pending_verification',
] as const
export type PollingUnitStatus = (typeof POLLING_UNIT_STATUSES)[number]

export type Coordinates = {
  latitude: number
  longitude: number
  precision: 'surveyed' | 'source_reported' | 'demo_approximate'
}

export type NoticeVerificationStatus = 'officially_confirmed' | 'awaiting_confirmation' | 'withdrawn'

export type OfficialNotice = {
  id: string
  kind: 'relocation' | 'temporary_closure'
  source_name: string | null
  source_url: string | null
  reference: string | null
  new_location_description: string | null
  effective_date: string | null
  received_at: string
  verification_status: NoticeVerificationStatus
}

export type RelocationReportSummary = {
  report_count: number
  first_reported_at: string
  last_reported_at: string
}

export type PollingUnitSummary = {
  id: string
  code: string
  name: string
  state: LocationRef
  lga: LocationRef
  ward: LocationRef
  address_description: string | null
  coordinates: Coordinates | null
  status: PollingUnitStatus
  source_name: string | null
  source_updated_at: string | null
  updated_at: string
}

export type PollingUnitDetail = PollingUnitSummary & {
  official_notices: OfficialNotice[]
  relocation_reports: RelocationReportSummary | null
}

export const UPDATE_CATEGORIES = [
  'polling_unit_relocation',
  'election_schedule',
  'voting_delay',
  'official_announcement',
  'security_notice',
  'general_information',
] as const
export type UpdateCategory = (typeof UPDATE_CATEGORIES)[number]

export const UPDATE_VERIFICATION_STATUSES = [
  'officially_confirmed',
  'independently_verified',
  'reported_unverified',
] as const
export type UpdateVerificationStatus = (typeof UPDATE_VERIFICATION_STATUSES)[number]

export type ElectionUpdate = {
  id: string
  title: string
  description: string
  category: UpdateCategory
  source_name: string
  source_url: string | null
  reference: string | null
  verification_status: UpdateVerificationStatus
  polling_unit_id: string | null
  published_at: string
  is_demo: boolean
}
