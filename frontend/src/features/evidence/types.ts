/** Mirrors backend/app/schemas/evidence.py and app/schemas/elections.py. */

export const EVIDENCE_STATUSES = [
  'received',
  'processing',
  'extracted',
  'arithmetic_validated',
  'cross_checked',
  'flagged_for_review',
  'under_human_review',
  'reviewed',
  'verified',
  'rejected',
] as const
export type EvidenceStatus = (typeof EVIDENCE_STATUSES)[number]

export type Party = { code: string; name: string }

export type Election = {
  id: string
  name: string
  election_label: string
  election_date: string
  template_id: string
  parties: Party[]
  is_demo: boolean
}

export type ElectionRef = { id: string; name: string; is_demo: boolean }

export type PollingUnitRef = {
  id: string
  code: string
  name: string
  state: string
  lga: string
  ward: string
}

export type EvidenceSummary = {
  id: string
  election: ElectionRef
  polling_unit: PollingUnitRef
  status: EvidenceStatus
  status_changed_at: string
  captured_at: string | null
  received_at: string
  original_sha256: string
  is_mine: boolean
  submitted_by: string | null
}

export type ProcessingStep = { step: string; applied: boolean } & Record<string, unknown>

export type EvidenceImage = {
  id: string
  kind: 'original' | 'processed'
  content_type: string
  byte_size: number
  width: number
  height: number
  sha256: string
  derived_from_id: string | null
  processing_steps: ProcessingStep[] | null
  created_at: string
}

export type EvidenceAction =
  | 'process'
  | 'correct'
  | 'validate'
  | 'start_review'
  | 'approve'
  | 'reject'
  | 'request_correction'

export type EvidenceDetail = EvidenceSummary & {
  template_id: string
  provenance: Record<string, unknown>
  processing_error: string | null
  images: EvidenceImage[]
  allowed_actions: EvidenceAction[]
  status_notice: string
}

export type SubmissionReceipt = { item: EvidenceDetail; created: boolean; message: string }

export type EvidencePage = {
  items: EvidenceSummary[]
  page: number
  page_size: number
  total: number
  total_pages: number
  status_notice: string
}

export type FieldValue = number | string | null

export type FieldVersion = {
  version: number
  origin: 'ocr' | 'human'
  value: FieldValue
  confidence: number | null
  source_text: string | null
  requires_review: boolean
  review_reasons: string[]
  reason: string | null
  created_by: string | null
  created_at: string
}

export type ExtractedField = {
  field_key: string
  label: string
  kind: 'integer' | 'text'
  required: boolean
  value: FieldValue
  origin: 'ocr' | 'human'
  confidence: number | null
  source_text: string | null
  bbox: { left: number; top: number; width: number; height: number } | null
  requires_review: boolean
  review_reasons: string[]
  version: number
  ocr_value: FieldValue
  ocr_confidence: number | null
  history: FieldVersion[]
}

export type Extraction = {
  id: string
  status: 'completed' | 'ocr_unavailable' | 'failed'
  provider: string
  provider_version: string | null
  template_id: string
  template_notice: string
  mean_confidence: number | null
  confidence_threshold: number
  error: string | null
  raw_text: string | null
  processed_image_id: string | null
  created_at: string
  fields: ExtractedField[]
  attention_fields: string[]
  disclaimer: string
}

export type FieldCorrection = { field_key: string; value: FieldValue; reason?: string; confirm?: boolean }

export type ValidationCheck = {
  rule_id: string
  description: string
  severity: 'error' | 'warning'
  outcome: 'passed' | 'failed' | 'not_evaluated'
  detail: string
  fields: string[]
  expected?: number | string
  actual?: number | string
}

export type ValidationReport = {
  template_id: string
  checks: ValidationCheck[]
  passed: string[]
  failed: string[]
  warnings: string[]
  missing_fields: string[]
  attention_fields: string[]
  summary: { errors: number; warnings: number }
  is_consistent: boolean
  disclaimer: string
  result_hash: string
  comparison_id: string
  analysis_run_id: string
  statistical_analysis: StatisticalSummary
}

export type Validation = {
  id: string
  passed: boolean
  result_hash: string
  is_current: boolean
  report: ValidationReport
  created_at: string
}

export type ComparisonField = {
  field_key: string
  status: 'match' | 'conflict' | 'incomplete'
  values: Record<string, FieldValue>
  most_common_value?: string
  differing_submissions?: string[]
  max_difference?: number
  relative_difference?: string
}

export type DuplicateIndicator = {
  type: 'identical_file' | 'near_duplicate_image' | 'same_submitter'
  submission_ids: string[]
  detail: string
  hamming_distance?: number
}

export type ComparisonReport = {
  submission_ids: string[]
  submission_count: number
  compared_fields: string[]
  fields: ComparisonField[]
  matching_fields: string[]
  conflicting_fields: string[]
  independently_matching_fields: string[]
  duplicates: DuplicateIndicator[]
  compared_at: string
  recommendation: { code: string; text: string }
}

export type Comparison = {
  id: string
  submission_ids: string[]
  has_conflicts: boolean
  has_duplicates: boolean
  report: ComparisonReport
  created_at: string
}

export type AlertSeverity = 'info' | 'low' | 'medium' | 'high'

export type AnomalyAlert = {
  id: string
  analysis_run_id: string
  category: 'ocr_uncertainty' | 'submission_discrepancy' | 'duplicate_evidence' | 'statistical'
  severity: AlertSeverity
  headline: string
  summary: string
  fields: string[]
  explanation: {
    what?: string
    why?: string
    contributing_fields?: Record<string, unknown>[]
    metrics?: Record<string, unknown>
  }
  recommendation: string
  model_name: string
  model_version: string
  is_demo: boolean
  is_current: boolean
  created_at: string
}

export type StatisticalContribution = {
  variable: string
  description: string
  value: string
  reference_median: string
  robust_z: string
  unusual: boolean
}

export type StatisticalSummary = {
  status: 'insufficient_data' | 'analysed'
  model_name: string
  model_version: string
  variables: string[]
  reference_records: number
  excluded_reference_records?: number
  min_samples: number
  is_demo: boolean
  detail?: string
  anomaly_score?: string
  empirical_p_value?: string
  alpha?: number
  is_outlier?: boolean
  contributing_fields?: StatisticalContribution[]
}

export type AnomalyReport = {
  alerts: AnomalyAlert[]
  statistical_analysis: StatisticalSummary | null
  disclaimer: string
}

export type AuditEvent = {
  id: string
  sequence: number
  action: string
  actor: string
  actor_id: string | null
  created_at: string
  details: Record<string, unknown>
  previous_hash: string
  event_hash: string
}

export type AuditTrail = {
  events: AuditEvent[]
  chain_valid: boolean
  head_hash: string | null
  broken_at_sequence: number | null
  problem: string | null
  notice: string
}

export type IntegrityReport = {
  submission_id: string
  original_sha256: string
  original_verified: boolean
  original_problem: string | null
  checked_at: string
  received_at: string
  captured_at: string | null
  images: EvidenceImage[]
  current_result_hash: string | null
  validated_result_hash: string | null
  result_hash_matches_validation: boolean | null
  audit_chain_valid: boolean
  audit_chain_length: number
  audit_head_hash: string | null
  hash_notes: Record<string, string>
}

export type ReviewAction = 'start' | 'approve' | 'reject' | 'request_correction'

export type ReviewOutcome = {
  review: { id: string; decision: string; notes: string | null; created_at: string }
  status: EvidenceStatus
  approvals: number
  approvals_required: number
  status_notice: string
}
