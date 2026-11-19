import { Badge } from '@/components/ui/badge'
import type { OfficialNotice, PollingUnitDetail, PollingUnitStatus } from '@/features/directory/types'

type Variant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral'

export const POLLING_UNIT_STATUS_META: Record<PollingUnitStatus, { label: string; variant: Variant; description: string }> =
  {
    active: {
      label: 'Active',
      variant: 'success',
      description: 'Location confirmed by the source.',
    },
    relocation_reported: {
      label: 'Relocation reported',
      variant: 'warning',
      description: 'Reported by the public. Not an official notice.',
    },
    officially_relocated: {
      label: 'Officially relocated',
      variant: 'info',
      description: 'Move confirmed by a named official source.',
    },
    temporarily_unavailable: {
      label: 'Temporarily unavailable',
      variant: 'destructive',
      description: 'May not be open at its listed location.',
    },
    pending_verification: {
      label: 'Information pending verification',
      variant: 'neutral',
      description: 'Details not yet confirmed by an official source.',
    },
  }

export function PollingUnitStatusBadge({ status }: { status: PollingUnitStatus }) {
  const meta = POLLING_UNIT_STATUS_META[status]
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

/** A notice counts as official only if it is confirmed and names its source. */
export function isOfficialNotice(notice: OfficialNotice) {
  return notice.verification_status === 'officially_confirmed' && Boolean(notice.source_name?.trim())
}

/**
 * Status to display. The API already refuses to mark a unit officially
 * relocated without a confirmed, sourced notice; this guard keeps the UI from
 * ever presenting such a claim if inconsistent data slips through.
 */
export function displayStatus(unit: Pick<PollingUnitDetail, 'status' | 'official_notices'>): PollingUnitStatus {
  if (unit.status !== 'officially_relocated') return unit.status
  const confirmed = unit.official_notices.some((notice) => notice.kind === 'relocation' && isOfficialNotice(notice))
  return confirmed ? 'officially_relocated' : 'pending_verification'
}
