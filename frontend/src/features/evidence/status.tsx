import {
  BadgeCheckIcon,
  BotIcon,
  CalculatorIcon,
  CircleDashedIcon,
  CircleXIcon,
  FileSearchIcon,
  GitCompareArrowsIcon,
  LoaderIcon,
  SearchIcon,
  TriangleAlertIcon,
  UserCheckIcon,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { AlertSeverity, EvidenceStatus } from '@/features/evidence/types'

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'destructive'

/** Statuses are assigned by the server. None of them is an INEC declaration. */
export const EVIDENCE_STATUS_META: Record<
  EvidenceStatus,
  { label: string; description: string; tone: Tone; icon: LucideIcon; stage: 'pending' | 'attention' | 'human' | 'final' }
> = {
  received: {
    label: 'Received',
    description: 'Original stored and fingerprinted. Not checked yet.',
    tone: 'neutral',
    icon: CircleDashedIcon,
    stage: 'pending',
  },
  processing: {
    label: 'Processing',
    description: 'The image is being prepared and read by OCR.',
    tone: 'info',
    icon: LoaderIcon,
    stage: 'pending',
  },
  extracted: {
    label: 'Extracted',
    description: 'Figures read or awaiting entry. Draft until checked.',
    tone: 'info',
    icon: FileSearchIcon,
    stage: 'pending',
  },
  arithmetic_validated: {
    label: 'Arithmetic consistent',
    description: 'The figures add up. This does not prove the sheet is authentic.',
    tone: 'info',
    icon: CalculatorIcon,
    stage: 'pending',
  },
  cross_checked: {
    label: 'Cross-checked',
    description: 'No conflicts with other submissions. Awaiting review.',
    tone: 'info',
    icon: GitCompareArrowsIcon,
    stage: 'pending',
  },
  flagged_for_review: {
    label: 'Needs review',
    description: 'A check needs a person to look: a failed rule, conflict, unclear OCR or AI alert.',
    tone: 'warning',
    icon: TriangleAlertIcon,
    stage: 'attention',
  },
  under_human_review: {
    label: 'Under human review',
    description: 'A reviewer is checking the image and figures.',
    tone: 'info',
    icon: SearchIcon,
    stage: 'human',
  },
  reviewed: {
    label: 'Reviewed',
    description: 'One reviewer approved. A second approval is needed.',
    tone: 'success',
    icon: UserCheckIcon,
    stage: 'human',
  },
  verified: {
    label: 'Verified by VoteTrace reviewers',
    description: 'Independent reviewers approved the figures. Not an INEC declaration.',
    tone: 'success',
    icon: BadgeCheckIcon,
    stage: 'final',
  },
  rejected: {
    label: 'Rejected',
    description: 'Rejected by a reviewer, with a reason.',
    tone: 'destructive',
    icon: CircleXIcon,
    stage: 'final',
  },
}

export function EvidenceStatusBadge({ status }: { status: EvidenceStatus }) {
  const meta = EVIDENCE_STATUS_META[status]
  const Icon = meta.icon
  return (
    <Badge variant={meta.tone} title={meta.description}>
      <Icon aria-hidden />
      {meta.label}
    </Badge>
  )
}

const SEVERITY_TONE: Record<AlertSeverity, Tone> = {
  info: 'neutral',
  low: 'info',
  medium: 'warning',
  high: 'destructive',
}

/** AI alerts get their own visual treatment so they are never mistaken for a verdict. */
export function AiAlertBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <Badge variant={SEVERITY_TONE[severity]}>
      <BotIcon aria-hidden />
      AI alert · {severity}
    </Badge>
  )
}

export function confidenceTone(confidence: number | null, threshold: number): Tone {
  if (confidence === null) return 'neutral'
  if (confidence < threshold / 2) return 'destructive'
  if (confidence < threshold) return 'warning'
  return 'success'
}

export function formatConfidence(confidence: number | null) {
  return confidence === null ? 'Not recorded' : `${Math.round(confidence * 100)}%`
}

export const REVIEW_REASON_LABELS: Record<string, string> = {
  low_confidence: 'Low OCR confidence',
  ambiguous_characters: 'Characters that resemble digits',
  not_found: 'Not found on the sheet',
  unexpected_format: 'Unexpected format',
  manual_entry_required: 'Manual entry required',
  missing_value: 'Value missing',
}

export function reviewReasonLabel(reason: string) {
  if (reason.startsWith('ambiguous:')) return `Read “${reason.slice('ambiguous:'.length)}”`
  return REVIEW_REASON_LABELS[reason] ?? reason.replaceAll('_', ' ')
}
