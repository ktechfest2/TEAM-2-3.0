import { createContext, useContext } from 'react'
import { useSearchParams } from 'react-router'
import { useElections } from '@/features/evidence/api'
import type { Election } from '@/features/evidence/types'
import type { AreaLevel } from '@/features/results/api'
import type { Level, UnitResultStatus } from '@/features/results/types'

export const DEMO_RESULT_LABEL = 'Sample data. Not an official election result.'

const integer = new Intl.NumberFormat('en-NG')

export function formatCount(value: number) {
  return integer.format(value)
}

export function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`
}

export const LEVEL_LABEL: Record<Level, string> = {
  national: 'National',
  state: 'State',
  lga: 'LGA',
  ward: 'Ward',
  polling_unit: 'Polling unit',
}

export const CHILD_LABEL: Record<AreaLevel, string> = {
  national: 'States',
  state: 'LGAs',
  lga: 'Wards',
  ward: 'Polling units',
}

/** Okabe–Ito palette: distinguishable with common colour-vision deficiencies. Not party colours. */
export const SERIES_COLOURS = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00', '#F0E442', '#000000']

export const UNIT_STATUS_META: Record<
  UnitResultStatus,
  { label: string; variant: 'neutral' | 'info' | 'success' | 'warning' | 'destructive'; description: string }
> = {
  not_reporting: {
    label: 'Not reporting',
    variant: 'neutral',
    description: 'No submission yet.',
  },
  pending: {
    label: 'Pending',
    variant: 'neutral',
    description: 'Received, not yet validated.',
  },
  reported: {
    label: 'Reported',
    variant: 'info',
    description: 'Submissions agree. Not yet reviewed.',
  },
  conflict: {
    label: 'Conflicting submissions',
    variant: 'warning',
    description: 'Submissions disagree. Left out of totals.',
  },
  verified: {
    label: 'Verified',
    variant: 'success',
    description: 'Approved by the required reviewers.',
  },
}

export type ResultsBase = { base: string; staff: boolean }

export const ResultsBaseContext = createContext<ResultsBase>({ base: '/results', staff: false })

export function useResultsBase() {
  return useContext(ResultsBaseContext)
}

const SEGMENT: Record<Exclude<Level, 'national'>, string> = {
  state: 'states',
  lga: 'lgas',
  ward: 'wards',
  polling_unit: 'polling-units',
}

export function resultsPath(base: string, level: Level, id: string | null | undefined, electionId: string | undefined) {
  const path = level === 'national' || !id ? base : `${base}/${SEGMENT[level]}/${encodeURIComponent(id)}`
  return electionId ? `${path}?election=${encodeURIComponent(electionId)}` : path
}

/** National-scope elections are the natural default for a national dashboard. */
export function preferredElection(items: Election[]) {
  return items.find((e) => e.election_label === 'PRESIDENTIAL') ?? items[0]
}

export function useSelectedElection() {
  const [params, setParams] = useSearchParams()
  const query = useElections()
  const items = query.data?.data.items ?? []
  const requested = params.get('election')
  const selected = items.find((e) => e.id === requested) ?? preferredElection(items)
  const select = (id: string) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set('election', id)
      return next
    })
  return { query, items, selected, select }
}
