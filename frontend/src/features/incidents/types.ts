/** Mirrors backend/app/schemas/incidents.py and the incident enums. */

export const INCIDENT_CATEGORIES = {
  violence: 'Electoral violence or threats',
  intimidation: 'Voter intimidation',
  vote_buying: 'Vote-buying allegation',
  delayed_officials: 'Delayed election officials',
  polling_unit_relocation: 'Polling-unit relocation',
  voting_disruption: 'Voting disruption',
  accessibility: 'Accessibility problem',
  misinformation: 'Misinformation',
  other: 'Other electoral concern',
} as const

export type IncidentCategory = keyof typeof INCIDENT_CATEGORIES

export const INCIDENT_STATUSES = {
  received: 'Received',
  screening: 'Screening',
  under_review: 'Under review',
  corroboration_required: 'Corroboration required',
  verified: 'Verified',
  unverified: 'Unverified',
  inconclusive: 'Inconclusive',
  rejected: 'Rejected',
  resolved: 'Resolved',
} as const

export type IncidentStatus = keyof typeof INCIDENT_STATUSES

export const INCIDENT_SEVERITIES = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' } as const

export type IncidentSeverity = keyof typeof INCIDENT_SEVERITIES

/** Public-facing stage. Keeps "reported" and "verified" visibly apart. */
export const INCIDENT_BANDS = {
  reported: 'Reported',
  under_review: 'Under review',
  corroborated: 'Corroborated',
  verified: 'Verified',
  inconclusive: 'Inconclusive',
  not_substantiated: 'Not substantiated',
} as const

export type IncidentBand = keyof typeof INCIDENT_BANDS

export const BAND_DESCRIPTIONS: Record<IncidentBand, string> = {
  reported: 'Received from the public. Not yet checked.',
  under_review: 'Reviewers are checking the report.',
  corroborated: 'Similar independent reports exist. Still not verified.',
  verified: 'Reviewers confirmed it against supporting evidence.',
  inconclusive: 'Reviewers could not confirm or rule it out.',
  not_substantiated: 'Reviewers found no support for it, or it was out of scope.',
}

export type ReporterKind = 'anonymous' | 'protected' | 'account'

export type LocationName = { id: string; name: string; code?: string | null }

export type IncidentReceipt = {
  id: string
  reference: string
  status: IncidentStatus
  band: IncidentBand
  received_at: string
  created: boolean
  duplicate: boolean
  personal_data_redacted: boolean
  attachment_stored: boolean
  notice: string
  privacy_notice: string
}

export type IncidentTrack = {
  reference: string
  band: IncidentBand
  band_label: string
  received_at: string
  last_updated_at: string
  public_summary: string | null
  notice: string
}

export type IncidentSummary = {
  id: string
  reference: string
  election_id: string
  category: IncidentCategory
  reported_category: IncidentCategory
  severity: IncidentSeverity
  status: IncidentStatus
  band: IncidentBand
  state: LocationName
  lga: LocationName
  ward: LocationName | null
  polling_unit: LocationName | null
  occurred_at: string
  time_is_approximate: boolean
  received_at: string
  status_changed_at: string
  excerpt: string
  has_attachment: boolean
  possible_duplicate_of: string | null
  similar_count: number
  missing_count: number
  reporter: ReporterKind
  is_public: boolean
}

export type IncidentPage = {
  items: IncidentSummary[]
  page: number
  page_size: number
  total: number
  total_pages: number
  notice: string
  generated_at: string
}

export type IncidentAttachment = {
  id: string
  content_type: string
  byte_size: number
  width: number
  height: number
  sha256: string
  created_at: string
}

export type IncidentReviewRecord = {
  id: string
  reviewer_id: string
  previous_status: IncidentStatus
  new_status: IncidentStatus
  reason: string
  evidence_refs: string[]
  category_from: IncidentCategory | null
  category_to: IncidentCategory | null
  severity_from: IncidentSeverity | null
  severity_to: IncidentSeverity | null
  public_summary: string | null
  published: boolean
  created_at: string
}

export type SimilarReport = { id: string; reference: string; similarity: number; same_polling_unit: boolean }

export type IncidentTriage = {
  method?: string
  classification?: {
    suggested_category: IncidentCategory | null
    agrees_with_reporter: boolean
    matched_keywords: Record<string, string[]>
    note: string
  }
  severity?: { level: IncidentSeverity; reasons: string[] }
  missing_information?: { field: string; message: string }[]
  personal_data_redacted?: boolean
  similar_reports?: SimilarReport[]
  corroborating_reports?: number
}

export type IncidentDetail = IncidentSummary & {
  description: string
  latitude: number | null
  longitude: number | null
  triage: IncidentTriage
  attachments: IncidentAttachment[]
  reviews: IncidentReviewRecord[]
  public_summary: string | null
  published_at: string | null
  resolution_basis: IncidentStatus | null
  reporter_user_id: string | null
  allowed_transitions: IncidentStatus[]
  can_review: boolean
  channel: string
}

export type IncidentReviewInput = {
  new_status: IncidentStatus
  reason: string
  evidence_refs: string[]
  category?: IncidentCategory
  severity?: IncidentSeverity
  publish?: boolean
  public_summary?: string
}

export type CountItem = { key: string; label: string; count: number }
export type AreaCount = { id: string; name: string; parent: string | null; count: number }

export type IncidentStats = {
  total: number
  awaiting_review: number
  under_investigation: number
  verified: number
  unverified: number
  inconclusive: number
  rejected: number
  resolved: number
  possible_duplicates: number
  critical_open: number
  by_category: CountItem[]
  by_status: CountItem[]
  by_severity: CountItem[]
  by_band: CountItem[]
  by_state: AreaCount[]
  by_lga: AreaCount[]
  timeline_bucket: 'hour' | 'day'
  timeline: { period: string; count: number }[]
  notice: string
  generated_at: string
}

export type PublicIncident = {
  category: IncidentCategory
  state: string
  lga: string
  occurred_on: string
  summary: string
  published_at: string
}

export type PublicIncidentSummary = {
  election_id: string
  by_band: CountItem[]
  published: PublicIncident[]
  notice: string
  demo_label: string | null
  generated_at: string
}

export type IncidentFilters = {
  electionId?: string
  stateId?: string
  lgaId?: string
  wardId?: string
  category?: IncidentCategory
  severity?: IncidentSeverity
  status?: IncidentStatus
  occurredFrom?: string
  occurredTo?: string
}
