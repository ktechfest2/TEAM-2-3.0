/** Sequential single-hue scale: darker means more polling units reporting, never which party leads. */
export const COVERAGE_BANDS = [
  { min: 75, colour: '#08519c', label: '75–100% reporting' },
  { min: 50, colour: '#3182bd', label: '50–74%' },
  { min: 25, colour: '#6baed6', label: '25–49%' },
  { min: 0.0001, colour: '#bdd7e7', label: 'Under 25%' },
  { min: 0, colour: '#eff3ff', label: 'None reporting' },
] as const

export function coverageColour(pct: number | null) {
  const value = pct ?? 0
  return COVERAGE_BANDS.find((band) => value >= band.min)?.colour ?? COVERAGE_BANDS[4].colour
}
