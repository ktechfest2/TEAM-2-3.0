import { z } from 'zod'
import { INCIDENT_CATEGORIES, type IncidentCategory } from '@/features/incidents/types'

export { INCIDENT_CATEGORIES, type IncidentCategory }

const categoryKeys = Object.keys(INCIDENT_CATEGORIES) as [IncidentCategory, ...IncidentCategory[]]
const MAX_AGE_MS = 90 * 24 * 60 * 60 * 1000
const CLOCK_SKEW_MS = 10 * 60 * 1000

const optionalNumber = (min: number, max: number, message: string) =>
  z
    .string()
    .trim()
    .refine((value) => value === '' || (Number.isFinite(Number(value)) && Number(value) >= min && Number(value) <= max), message)

/** Client-side checks for quick feedback. The server repeats every one. */
export const incidentReportSchema = z
  .object({
    electionId: z.string().min(1, 'Choose the election'),
    category: z.enum(categoryKeys, { error: 'Select a category' }),
    stateId: z.string().min(1, 'Choose the state'),
    lgaId: z.string().min(1, 'Choose the LGA'),
    wardId: z.string(),
    pollingUnitId: z.string(),
    occurredAt: z
      .string()
      .min(1, 'Enter when the incident happened')
      .refine((value) => !Number.isNaN(Date.parse(value)), 'Enter a valid date and time')
      .refine((value) => Date.parse(value) <= Date.now() + CLOCK_SKEW_MS, 'The time cannot be in the future')
      .refine((value) => Date.parse(value) >= Date.now() - MAX_AGE_MS, 'Reports must be about the last 90 days'),
    timeIsApproximate: z.boolean(),
    description: z
      .string()
      .trim()
      .min(20, 'Describe what happened in at least 20 characters')
      .max(2000, 'Keep the description under 2,000 characters'),
    latitude: optionalNumber(-90, 90, 'Latitude must be between -90 and 90'),
    longitude: optionalNumber(-180, 180, 'Longitude must be between -180 and 180'),
    identity: z.enum(['anonymous', 'protected', 'account']),
  })
  .refine((value) => (value.latitude === '') === (value.longitude === ''), {
    message: 'Give both latitude and longitude, or neither',
    path: ['longitude'],
  })

export type IncidentReportInput = z.infer<typeof incidentReportSchema>
