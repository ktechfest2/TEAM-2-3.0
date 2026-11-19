import { MapIcon, MapPinOffIcon, WifiOffIcon } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { LoadingState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import type { MapUnit } from '@/features/polling-units/polling-unit-map'
import { useOnlineStatus } from '@/lib/offline/use-online-status'

const PollingUnitMap = lazy(() => import('@/features/polling-units/polling-unit-map'))

type MapPanelProps = {
  units: MapUnit[]
  selectedId?: string
  onSelect?: (id: string) => void
}

function Fallback({ icon: Icon, children }: { icon: typeof MapIcon; children: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-dashed bg-surface px-4 py-6 text-sm text-muted-foreground">
      <Icon className="size-5 shrink-0" aria-hidden />
      <p>{children}</p>
    </div>
  )
}

/** Loads the map only on request, to save data on slow connections. */
export function MapPanel({ units, selectedId, onSelect }: MapPanelProps) {
  const online = useOnlineStatus()
  const [requested, setRequested] = useState(false)
  const mappable = units.filter((unit) => unit.coordinates)
  const hasDemoPositions = mappable.some((unit) => unit.coordinates?.precision === 'demo_approximate')

  if (mappable.length === 0) {
    return <Fallback icon={MapPinOffIcon}>No map coordinates are available from the source for these polling units.</Fallback>
  }
  if (!online) {
    return <Fallback icon={WifiOffIcon}>The map is unavailable offline. Polling-unit details are listed instead.</Fallback>
  }
  if (!requested && !selectedId) {
    return (
      <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed bg-surface px-4 py-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          {mappable.length} of {units.length} polling units have map coordinates. The map uses extra data.
        </p>
        <Button type="button" variant="outline" onClick={() => setRequested(true)}>
          <MapIcon />
          Show map
        </Button>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {hasDemoPositions && (
        <p className="text-xs text-muted-foreground">Pins are approximate, placed near the LGA centre.</p>
      )}
      <Suspense fallback={<LoadingState label="Loading map" />}>
        <PollingUnitMap units={units} selectedId={selectedId} onSelect={onSelect} />
      </Suspense>
    </div>
  )
}
