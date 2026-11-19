import { MapPinIcon } from 'lucide-react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/features/directory/data-notice'
import type { Coordinates, PollingUnitSummary } from '@/features/directory/types'
import { PollingUnitStatusBadge } from '@/features/polling-units/status'
import { cn } from '@/lib/utils'

export function formatCoordinates(coordinates: Coordinates | null) {
  if (!coordinates) return 'Not available from source'
  const text = `${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)}`
  return coordinates.precision === 'demo_approximate' ? `${text} (approximate)` : text
}

export function PollingUnitFacts({ unit }: { unit: PollingUnitSummary }) {
  const rows: [string, string][] = [
    ['Code', unit.code],
    ['State', unit.state.name],
    ['LGA', unit.lga.name],
    ['Ward', unit.ward.name],
    ['Address or location', unit.address_description ?? 'Not available from source'],
    ['Coordinates', formatCoordinates(unit.coordinates)],
    ['Information source', unit.source_name ?? 'Source not yet confirmed'],
    ['Source last updated', formatDateTime(unit.source_updated_at)],
    ['Record last updated', formatDateTime(unit.updated_at)],
  ]
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

type PollingUnitCardProps = {
  unit: PollingUnitSummary
  selected?: boolean
  onShowOnMap?: (id: string) => void
}

export function PollingUnitCard({ unit, selected, onShowOnMap }: PollingUnitCardProps) {
  return (
    <article
      aria-labelledby={`pu-${unit.id}`}
      className={cn('rounded-lg border bg-card p-4', selected && 'border-primary ring-2 ring-primary/30')}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 id={`pu-${unit.id}`} className="text-base font-semibold">
          <Link to={`/polling-units/${unit.id}`} className="hover:underline">
            {unit.name}
          </Link>
        </h3>
        <div className="flex flex-wrap gap-1.5">
          <PollingUnitStatusBadge status={unit.status} />
        </div>
      </div>
      <div className="mt-3">
        <PollingUnitFacts unit={unit} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild size="sm">
          <Link to={`/polling-units/${unit.id}`}>View details</Link>
        </Button>
        {unit.coordinates && onShowOnMap && (
          <Button type="button" size="sm" variant="outline" onClick={() => onShowOnMap(unit.id)}>
            <MapPinIcon />
            Show on map
          </Button>
        )}
      </div>
    </article>
  )
}
