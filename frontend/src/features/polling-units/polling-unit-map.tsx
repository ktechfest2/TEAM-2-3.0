import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { LocateFixedIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { PollingUnitSummary } from '@/features/directory/types'

export type MapUnit = Pick<PollingUnitSummary, 'id' | 'name' | 'code' | 'coordinates'>

type PollingUnitMapProps = {
  units: MapUnit[]
  selectedId?: string
  onSelect?: (id: string) => void
}

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const NIGERIA_CENTER: L.LatLngTuple = [9.08, 8.68]

function popupContent(unit: MapUnit) {
  const root = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = unit.name
  const code = document.createElement('div')
  code.textContent = unit.code
  root.append(name, code)
  if (unit.coordinates?.precision === 'demo_approximate') {
    const note = document.createElement('div')
    note.textContent = 'Approximate position'
    root.append(note)
  }
  return root
}

export default function PollingUnitMap({ units, selectedId, onSelect }: PollingUnitMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)
  const markersRef = useRef(new Map<string, L.CircleMarker>())
  const onSelectRef = useRef(onSelect)
  const [locateError, setLocateError] = useState<string | null>(null)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    if (!containerRef.current) return
    const map = L.map(containerRef.current, { center: NIGERIA_CENTER, zoom: 6, scrollWheelZoom: false })
    L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 18 }).addTo(map)
    layerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return
    layer.clearLayers()
    markersRef.current.clear()
    const points: L.LatLngTuple[] = []
    for (const unit of units) {
      if (!unit.coordinates) continue
      const point: L.LatLngTuple = [unit.coordinates.latitude, unit.coordinates.longitude]
      points.push(point)
      const marker = L.circleMarker(point, { radius: 9, weight: 2, color: '#011b33', fillOpacity: 0.6 })
        .bindPopup(popupContent(unit))
        .bindTooltip(unit.name)
        .on('click', () => onSelectRef.current?.(unit.id))
      marker.addTo(layer)
      markersRef.current.set(unit.id, marker)
    }
    const [only] = points
    if (points.length === 1 && only) map.setView(only, 14)
    else if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [24, 24], maxZoom: 15 })
  }, [units])

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const selected = id === selectedId
      marker.setStyle({ color: selected ? '#b45309' : '#011b33', fillOpacity: selected ? 0.9 : 0.6 })
      if (selected) {
        marker.bringToFront()
        marker.openPopup()
      }
    }
  }, [selectedId, units])

  const locate = () => {
    setLocateError(null)
    if (!('geolocation' in navigator)) {
      setLocateError('Location is not available in this browser.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const map = mapRef.current
        if (!map) return
        const here: L.LatLngTuple = [coords.latitude, coords.longitude]
        L.circleMarker(here, { radius: 7, color: '#1d4ed8', fillOpacity: 0.9 }).bindTooltip('Your location').addTo(map)
        map.setView(here, 14)
      },
      () => setLocateError('Your location could not be determined. Check location permissions.'),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  }

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        className="h-80 w-full overflow-hidden rounded-lg border sm:h-96"
        role="region"
        aria-label="Map of polling units"
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={locate}>
          <LocateFixedIcon />
          Show my location
        </Button>
        <p className="text-xs text-muted-foreground">Your location is used only on this device and never sent to VoteTrace.</p>
      </div>
      {locateError && (
        <p role="alert" className="text-xs font-medium text-destructive">
          {locateError}
        </p>
      )}
    </div>
  )
}
