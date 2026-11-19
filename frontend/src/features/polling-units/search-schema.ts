import { z } from 'zod'

/** Mirrors the backend `q` pattern: letters in any script, digits and place-name punctuation. */
const SEARCH_TEXT = /^[\p{L}\p{N}_\s\-'.,/()]+$/u

export const pollingUnitSearchSchema = z.object({
  q: z
    .string()
    .trim()
    .refine((value) => value === '' || value.length >= 2, 'Enter at least 2 characters.')
    .refine((value) => value.length <= 80, 'Use 80 characters or fewer.')
    .refine(
      (value) => value === '' || SEARCH_TEXT.test(value),
      'Use letters, numbers, spaces and basic punctuation only.',
    ),
})

export type PollingUnitSearchInput = z.infer<typeof pollingUnitSearchSchema>
