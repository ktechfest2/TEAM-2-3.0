import { Badge } from '@/components/ui/badge'
import {
  INCIDENT_BANDS,
  INCIDENT_SEVERITIES,
  INCIDENT_STATUSES,
  type IncidentBand,
  type IncidentSeverity,
  type IncidentStatus,
} from '@/features/incidents/types'
import { useT } from '@/i18n/locale-provider'

type Variant = 'neutral' | 'info' | 'warning' | 'success' | 'destructive' | 'outline'

const BAND_VARIANT: Record<IncidentBand, Variant> = {
  reported: 'neutral',
  under_review: 'info',
  corroborated: 'warning',
  verified: 'success',
  inconclusive: 'outline',
  not_substantiated: 'outline',
}

const STATUS_VARIANT: Record<IncidentStatus, Variant> = {
  received: 'neutral',
  screening: 'info',
  under_review: 'info',
  corroboration_required: 'warning',
  verified: 'success',
  unverified: 'outline',
  inconclusive: 'outline',
  rejected: 'outline',
  resolved: 'neutral',
}

const SEVERITY_VARIANT: Record<IncidentSeverity, Variant> = {
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  critical: 'destructive',
}

export function BandBadge({ band }: { band: IncidentBand }) {
  const t = useT()
  return <Badge variant={BAND_VARIANT[band]}>{t(INCIDENT_BANDS[band])}</Badge>
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const t = useT()
  return <Badge variant={STATUS_VARIANT[status]}>{t(INCIDENT_STATUSES[status])}</Badge>
}

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  const t = useT()
  return <Badge variant={SEVERITY_VARIANT[severity]}>{t(INCIDENT_SEVERITIES[severity])}</Badge>
}
