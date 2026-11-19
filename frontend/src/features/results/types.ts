import type { DataSource } from '@/features/directory/types'

/** Mirrors backend/app/schemas/analytics.py. */

export type Level = 'national' | 'state' | 'lga' | 'ward' | 'polling_unit'
export type DataStatus = 'demonstration' | 'live'
export type UnitResultStatus = 'not_reporting' | 'pending' | 'reported' | 'conflict' | 'verified'

export type ElectionRef = { id: string; name: string; election_label: string; is_demo: boolean }
export type AreaRef = { level: Level; id: string | null; name: string; code: string | null }

export type Coverage = {
  expected_polling_units: number
  polling_units_with_submissions: number
  reporting_polling_units: number
  verified_polling_units: number
  pending_polling_units: number
  flagged_polling_units: number
  conflict_polling_units: number
  anomaly_polling_units: number
  submission_count: number
  independent_submission_count: number
  rejected_submission_count: number
  incomplete_registry_entries: number
  reporting_coverage_pct: number | null
  verification_coverage_pct: number | null
  reporting_label: string
  verification_label: string
}

export type AreaSummary = {
  area: AreaRef
  iso_code: string | null
  coverage: Coverage
  last_updated_at: string | null
}

export type PartyTotal = { code: string; name: string; votes: number; share_pct: number | null }

export type StreamTotals = {
  stream: 'reported' | 'verified'
  description: string
  polling_units_included: number
  expected_polling_units: number
  registered_voters: number
  accredited_voters: number
  total_valid_votes: number
  rejected_votes: number
  total_votes_cast: number
  parties: PartyTotal[]
  share_basis: string
}

export type AlertSummary = {
  kind: 'unresolved_discrepancies' | 'records_requiring_review' | 'unusual_patterns' | 'incomplete'
  count: number
  title: string
  description: string
  href: string | null
}

type Envelope = {
  election: ElectionRef
  data_status: DataStatus
  demo_label: string | null
  notice: string
  generated_at: string
}

export type AreaResponse = Envelope & {
  level: Level
  summary: AreaSummary
  breadcrumbs: AreaRef[]
  reported: StreamTotals
  verified: StreamTotals
  child_level: Level | null
  children: AreaSummary[]
  child_areas_reporting: number
  child_areas_outstanding: number
  alerts: AlertSummary[]
  partial_notice: string
  provenance: {
    aggregation_level: Level
    registry_source: DataSource
    method: string
    source_records_path: string
  }
}

export type AreaListResponse = Envelope & {
  level: Level
  items: AreaSummary[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export type PartyResultsResponse = Envelope & {
  area: AreaRef
  reported: StreamTotals
  verified: StreamTotals
  breakdown_level: Level | null
  breakdown: { area: AreaRef; reported: StreamTotals; verified: StreamTotals }[]
  partial_notice: string
}

export type PollingUnitRow = {
  id: string
  code: string
  name: string
  ward: AreaRef
  lga: AreaRef
  state: AreaRef
  status: UnitResultStatus
  submission_count: number
  accepted_count: number
  independent_count: number
  distinct_results: number
  has_flagged: boolean
  has_anomaly: boolean
  reported_result_hash: string | null
  verified_result_hash: string | null
  registry_incomplete: boolean
  revision: number | null
  updated_at: string | null
}

export type PollingUnitPage = Envelope & {
  items: PollingUnitRow[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export type SourceRecord = {
  submission_id: string
  workflow_status: string
  received_at: string
  result_fingerprint: string | null
  validation_passed: boolean | null
  agrees_with_reported: boolean | null
  contributes: boolean
}

export type PollingUnitResultResponse = Envelope & {
  unit: PollingUnitRow
  breadcrumbs: AreaRef[]
  reported: StreamTotals
  verified: StreamTotals
  verification: {
    status: UnitResultStatus
    required_approvals: number
    approvals_on_verified_result: number
    verified_at: string | null
    checks_passed: number
    checks_failed: number
    warnings: number
    disclaimer: string
  }
  source_records: SourceRecord[]
}

export type ProgressResponse = Omit<Envelope, 'notice'> & {
  area: AreaRef
  expected_polling_units: number
  bucket: 'hour'
  points: { at: string; reporting_polling_units: number; verified_polling_units: number }[]
  description: string
}

export type DiscrepancyKind = 'conflict' | 'flagged' | 'anomaly' | 'pending' | 'incomplete'
