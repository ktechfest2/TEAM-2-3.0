import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef, useState } from 'react'
import { formatPct } from '@/features/results/format'
import { COVERAGE_BANDS, coverageColour } from '@/features/results/map-scale'
import type { AreaSummary } from '@/features/results/types'

type NigeriaMapProps = {
  states: AreaSummary[]
  onSelect: (stateId: string) => void
}

type StateFeature = GeoJSON.Feature<GeoJSON.Geometry, { iso_code: string; name: string }>
type Boundaries = GeoJSON.FeatureCollection<GeoJSON.Geometry, StateFeature['properties']> & { attribution?: string }

export const BOUNDARIES_URL = '/geo/nigeria-states.geojson'

function tooltip(name: string, summary: AreaSummary | undefined) {
  const root = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = name
  const line = document.createElement('div')
  line.textContent = summary
    ? `${summary.coverage.reporting_polling_units} / ${summary.coverage.expected_polling_units} reporting (${formatPct(summary.coverage.reporting_coverage_pct)}) · ${summary.coverage.verified_polling_units} verified`
    : 'No polling units in the register for this election'
  root.append(title, line)
  return root
}

/** Choropleth of reporting coverage. No base tiles: the boundaries are the whole map. */
export default function NigeriaMap({ states, onSelect }: NigeriaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.GeoJSON | null>(null)
  const onSelectRef = useRef(onSelect)
  const [boundaries, setBoundaries] = useState<Boundaries | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    let cancelled = false
    fetch(BOUNDARIES_URL)
      .then((response) => (response.ok ? (response.json() as Promise<Boundaries>) : Promise.reject(response)))
      .then((data) => !cancelled && setBoundaries(data))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!containerRef.current) return
    const map = L.map(containerRef.current, {
      center: [9.08, 8.68],
      zoom: 5.5,
      zoomSnap: 0.25,
      scrollWheelZoom: false,
      attributionControl: true,
    })
    map.getContainer().style.background = 'var(--muted)'
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !boundaries) return
    layerRef.current?.remove()
    const byIso = new Map(states.filter((s) => s.iso_code).map((s) => [s.iso_code, s]))
    const layer = L.geoJSON(boundaries, {
      attribution: boundaries.attribution,
      style: (feature) => {
        const summary = byIso.get(feature?.properties.iso_code)
        return {
          color: '#ffffff',
          weight: 1,
          fillOpacity: summary ? 0.85 : 0.35,
          fillColor: summary ? coverageColour(summary.coverage.reporting_coverage_pct) : '#9ca3af',
          dashArray: summary ? undefined : '3 3',
        }
      },
      onEachFeature: (feature: StateFeature, featureLayer) => {
        const summary = byIso.get(feature.properties.iso_code)
        featureLayer.bindTooltip(tooltip(feature.properties.name, summary), { sticky: true })
        if (summary?.area.id) {
          const id = summary.area.id
          featureLayer.on('click', () => onSelectRef.current(id))
          featureLayer.on('mouseover', () => (featureLayer as L.Path).setStyle({ weight: 2.5, color: '#111827' }))
          featureLayer.on('mouseout', () => (featureLayer as L.Path).setStyle({ weight: 1, color: '#ffffff' }))
        }
      },
    }).addTo(map)
    layerRef.current = layer
    map.fitBounds(layer.getBounds(), { padding: [8, 8] })
  }, [boundaries, states])

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        className="h-[22rem] w-full overflow-hidden rounded-lg border sm:h-[28rem]"
        role="region"
        aria-label="Map of Nigerian states coloured by reporting coverage. Use the table below for keyboard access."
      />
      {failed && (
        <p className="text-sm text-muted-foreground">
          State boundaries could not be loaded. Use the state table instead.
        </p>
      )}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Map legend">
        {COVERAGE_BANDS.map((band) => (
          <li key={band.label} className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-sm" style={{ background: band.colour }} aria-hidden /> {band.label}
          </li>
        ))}
        <li className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-sm border border-dashed border-gray-500 bg-gray-400/40" aria-hidden /> Not in
          the register for this election
        </li>
      </ul>
    </div>
  )
}
