import { FormField } from '@/components/forms/form-field'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/input'
import { useLgas, useStates, useWards } from '@/features/directory/api'
import { useT } from '@/i18n/locale-provider'

export type LocationValue = { stateId?: string; lgaId?: string; wardId?: string }

type Level = 'state' | 'lga' | 'ward'

type LocationSelectProps = {
  value: LocationValue
  onChange: (value: LocationValue) => void
  /** Deepest level to offer. Defaults to ward. */
  depth?: Level
  idPrefix?: string
  /** Form mode: "Choose a ..." placeholders instead of filter-style "All ...". */
  pick?: boolean
  required?: readonly Level[]
  errors?: Partial<Record<Level, string>>
}

/** Cascading State → LGA → Ward selects. Changing a level clears the levels below it. */
export function LocationSelect({
  value,
  onChange,
  depth = 'ward',
  idPrefix = 'location',
  pick = false,
  required = [],
  errors = {},
}: LocationSelectProps) {
  const t = useT()
  const states = useStates()
  const lgas = useLgas(depth === 'state' ? undefined : value.stateId)
  const wards = useWards(depth === 'ward' ? value.lgaId : undefined)
  const errorText = (isError: boolean, what: string) =>
    isError ? t('{what} could not be loaded. Check your connection and try again.', { what }) : undefined

  const stateError = errorText(states.isError, t('States')) ?? errors.state
  const lgaError = errorText(lgas.isError, t('LGAs')) ?? errors.lga
  const wardError = errorText(wards.isError, t('Wards')) ?? errors.ward
  const errorId = (level: string, error?: string) => (error ? `${idPrefix}-${level}-error` : undefined)
  const retry = (query: { isError: boolean; refetch: () => unknown }) =>
    query.isError ? (
      <Button type="button" variant="outline" size="sm" className="mt-1.5" onClick={() => void query.refetch()}>
        {t('Try again')}
      </Button>
    ) : null

  return (
    <div className="grid min-w-0 gap-4 md:grid-cols-3">
      <FormField id={`${idPrefix}-state`} label={t('State')} error={stateError} required={required.includes('state')}>
        <Select
          id={`${idPrefix}-state`}
          value={value.stateId ?? ''}
          disabled={states.isPending && !states.isError}
          aria-invalid={Boolean(stateError)}
          aria-describedby={errorId('state', stateError)}
          onChange={(event) => onChange({ stateId: event.target.value || undefined })}
        >
          <option value="">
            {states.isPending ? t('Loading states…') : pick ? t('Choose a state') : t('All states')}
          </option>
          {states.data?.data.items.map((state) => (
            <option key={state.id} value={state.id}>
              {state.name}
            </option>
          ))}
        </Select>
        {retry(states)}
      </FormField>

      {depth !== 'state' && (
        <FormField
          id={`${idPrefix}-lga`}
          label={t('Local Government Area')}
          error={lgaError}
          required={required.includes('lga')}
        >
          <Select
            id={`${idPrefix}-lga`}
            value={value.lgaId ?? ''}
            disabled={!value.stateId || lgas.isPending}
            aria-invalid={Boolean(lgaError)}
            aria-describedby={errorId('lga', lgaError)}
            onChange={(event) => onChange({ stateId: value.stateId, lgaId: event.target.value || undefined })}
          >
            <option value="">
              {!value.stateId ? t('Choose a state first') : pick ? t('Choose an LGA') : t('All LGAs')}
            </option>
            {lgas.data?.data.items.map((lga) => (
              <option key={lga.id} value={lga.id}>
                {lga.name}
              </option>
            ))}
          </Select>
          {retry(lgas)}
        </FormField>
      )}

      {depth === 'ward' && (
        <FormField id={`${idPrefix}-ward`} label={t('Ward')} error={wardError} required={required.includes('ward')}>
          <Select
            id={`${idPrefix}-ward`}
            value={value.wardId ?? ''}
            disabled={!value.lgaId || wards.isPending}
            aria-invalid={Boolean(wardError)}
            aria-describedby={errorId('ward', wardError)}
            onChange={(event) =>
              onChange({ stateId: value.stateId, lgaId: value.lgaId, wardId: event.target.value || undefined })
            }
          >
            <option value="">
              {!value.lgaId
                ? t('Choose an LGA first')
                : !pick
                  ? t('All wards')
                  : required.includes('ward')
                    ? t('Choose a ward')
                    : t('Choose a ward (optional)')}
            </option>
            {wards.data?.data.items.map((ward) => (
              <option key={ward.id} value={ward.id}>
                {ward.name}
              </option>
            ))}
          </Select>
          {retry(wards)}
        </FormField>
      )}
    </div>
  )
}
