import { CheckCircle2Icon, CircleDashedIcon, CircleXIcon, SearchIcon, TriangleAlertIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useT } from '@/i18n/locale-provider'

/** Mirrors backend `VerificationStatus`. Status is assigned server-side only. */
export const VERIFICATION_STATUSES = ['pending', 'under_review', 'verified', 'discrepancy', 'rejected'] as const

export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number]

export const VERIFICATION_STATUS_META: Record<
  VerificationStatus,
  {
    label: string
    description: string
    variant: 'neutral' | 'info' | 'success' | 'warning' | 'destructive'
    icon: typeof CheckCircle2Icon
  }
> = {
  pending: {
    label: 'Pending',
    description: 'Received. No checks completed yet.',
    variant: 'neutral',
    icon: CircleDashedIcon,
  },
  under_review: {
    label: 'Under review',
    description: 'A reviewer is checking the evidence.',
    variant: 'info',
    icon: SearchIcon,
  },
  verified: {
    label: 'Verified',
    description: 'Evidence matches the recorded figures.',
    variant: 'success',
    icon: CheckCircle2Icon,
  },
  discrepancy: {
    label: 'Discrepancy',
    description: 'Evidence differs from the recorded figures.',
    variant: 'warning',
    icon: TriangleAlertIcon,
  },
  rejected: {
    label: 'Rejected',
    description: 'Unreadable, incomplete or not linked to a polling unit.',
    variant: 'destructive',
    icon: CircleXIcon,
  },
}

export function VerificationStatusBadge({ status }: { status: VerificationStatus }) {
  const t = useT()
  const meta = VERIFICATION_STATUS_META[status]
  const Icon = meta.icon
  return (
    <Badge variant={meta.variant}>
      <Icon aria-hidden />
      {t(meta.label)}
    </Badge>
  )
}
