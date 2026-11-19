import { BadgeCheckIcon, CircleHelpIcon, ShieldCheckIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { UpdateCategory, UpdateVerificationStatus } from '@/features/directory/types'

export const UPDATE_CATEGORY_LABEL: Record<UpdateCategory, string> = {
  polling_unit_relocation: 'Polling-unit relocation',
  election_schedule: 'Election schedule',
  voting_delay: 'Voting delay',
  official_announcement: 'Official announcement',
  security_notice: 'Security notice',
  general_information: 'General information',
}

export const UPDATE_VERIFICATION_META: Record<
  UpdateVerificationStatus,
  { label: string; variant: 'success' | 'info' | 'warning'; description: string; icon: typeof BadgeCheckIcon }
> = {
  officially_confirmed: {
    label: 'Officially confirmed',
    variant: 'success',
    description: 'Confirmed by a named official source.',
    icon: BadgeCheckIcon,
  },
  independently_verified: {
    label: 'Independently verified',
    variant: 'info',
    description: 'Checked against independent sources. Not an official announcement.',
    icon: ShieldCheckIcon,
  },
  reported_unverified: {
    label: 'Reported, awaiting verification',
    variant: 'warning',
    description: 'Not yet verified. Treat with caution.',
    icon: CircleHelpIcon,
  },
}

export function UpdateVerificationBadge({ status }: { status: UpdateVerificationStatus }) {
  const meta = UPDATE_VERIFICATION_META[status]
  return (
    <Badge variant={meta.variant}>
      <meta.icon aria-hidden />
      {meta.label}
    </Badge>
  )
}
