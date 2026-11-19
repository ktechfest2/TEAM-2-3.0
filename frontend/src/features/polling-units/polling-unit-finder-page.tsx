import { zodResolver } from '@hookform/resolvers/zod'
import { MapPinnedIcon, SearchIcon, SearchXIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useSearchParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { describedBy, FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { usePollingUnitSearch } from '@/features/directory/api'
import { DataSourceNotice, FreshnessNote } from '@/features/directory/data-notice'
import { LocationSelect, type LocationValue } from '@/features/directory/location-select'
import { MapPanel } from '@/features/polling-units/map-panel'
import { PollingUnitCard } from '@/features/polling-units/polling-unit-card'
import { pollingUnitSearchSchema, type PollingUnitSearchInput } from '@/features/polling-units/search-schema'
import { useT } from '@/i18n/locale-provider'
import { ApiError } from '@/lib/api-client'

const PAGE_SIZE = 10

function readParam(params: URLSearchParams, key: string) {
  return params.get(key) || undefined
}

export function PollingUnitFinderPage() {
  const t = useT()
  const searchHint = t('For example a polling-unit name, or a code in the INEC format SS-LL-WW-PPP')
  const [params, setParams] = useSearchParams()
  const [selectedId, setSelectedId] = useState<string>()

  const location: LocationValue = {
    stateId: readParam(params, 'state'),
    lgaId: readParam(params, 'lga'),
    wardId: readParam(params, 'ward'),
  }
  const q = readParam(params, 'q')
  const page = Math.max(1, Number(params.get('page')) || 1)
  const hasCriteria = Boolean(location.stateId || q)

  const search = usePollingUnitSearch({ ...location, q, page, pageSize: PAGE_SIZE }, hasCriteria)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PollingUnitSearchInput>({
    resolver: zodResolver(pollingUnitSearchSchema),
    defaultValues: { q: q ?? '' },
  })

  useEffect(() => {
    reset({ q: q ?? '' })
  }, [q, reset])

  const update = (next: Partial<Record<'state' | 'lga' | 'ward' | 'q', string | undefined>>) => {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    merged.delete('page')
    setSelectedId(undefined)
    setParams(merged)
  }

  const onLocationChange = (value: LocationValue) =>
    update({ state: value.stateId, lga: value.lgaId, ward: value.wardId })

  const onSubmit = handleSubmit((values) => update({ q: values.q || undefined }))

  const goToPage = (next: number) => {
    const merged = new URLSearchParams(params)
    if (next > 1) merged.set('page', String(next))
    else merged.delete('page')
    setSelectedId(undefined)
    setParams(merged)
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t('Polling units')}
        title={t('Find your polling unit')}
        description={t('Search by state, local government area, ward, polling-unit name or code.')}
      />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={onSubmit} noValidate role="search" aria-label={t('Polling units')} className="space-y-5">
            <FormField
              id="pu-search"
              label={t('Polling-unit name or code')}
              hint={searchHint}
              error={errors.q?.message}
            >
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="pu-search"
                  type="search"
                  autoComplete="off"
                  inputMode="search"
                  maxLength={80}
                  aria-invalid={Boolean(errors.q)}
                  aria-describedby={describedBy('pu-search', errors.q?.message, searchHint)}
                  {...register('q')}
                />
                <Button type="submit" className="sm:w-32">
                  <SearchIcon />
                  {t('Search')}
                </Button>
              </div>
            </FormField>
            <LocationSelect value={location} onChange={onLocationChange} idPrefix="pu" />
            {hasCriteria && (
              <Button type="button" variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams())}>
                {t('Clear search')}
              </Button>
            )}
          </form>
        </CardContent>
      </Card>

      <section aria-labelledby="pu-results-heading" className="space-y-4">
        <h2 id="pu-results-heading" className="text-lg font-semibold">
          {t('Results')}
        </h2>
        <Results
          hasCriteria={hasCriteria}
          search={search}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onPage={goToPage}
        />
      </section>
    </div>
  )
}

type ResultsProps = {
  hasCriteria: boolean
  search: ReturnType<typeof usePollingUnitSearch>
  selectedId?: string
  onSelect: (id: string) => void
  onPage: (page: number) => void
}

function Results({ hasCriteria, search, selectedId, onSelect, onPage }: ResultsProps) {
  const t = useT()
  if (!hasCriteria) {
    return (
      <EmptyState
        icon={MapPinnedIcon}
        title={t('Choose a state or enter a search')}
        description={t('Select a state, LGA and ward, or search by polling-unit name or code.')}
      />
    )
  }
  if (search.isPending) return <LoadingState variant="skeleton" rows={3} label={t('Searching polling units')} />
  if (search.isError) {
    const offline = search.error instanceof ApiError && search.error.status === 0
    return (
      <ErrorState
        title={offline ? t('You are offline') : t('Search failed')}
        message={
          offline
            ? t('This search has not been saved on this device yet. Reconnect and try again.')
            : t('Polling units could not be loaded. Please try again.')
        }
        onRetry={() => void search.refetch()}
      />
    )
  }

  const { data: page, origin, syncedAt } = search.data

  return (
    <div className="space-y-4">
      <DataSourceNotice source={page.data_source} />
      <FreshnessNote result={{ origin, syncedAt }} />
      {page.items.length === 0 ? (
        <EmptyState
          icon={SearchXIcon}
          title={t('No polling units match your search')}
          description={t('Check the spelling or code, or widen the location filters.')}
        />
      ) : (
        <>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {t('Showing {from}–{to} of {total} polling units', {
              from: (page.page - 1) * page.page_size + 1,
              to: (page.page - 1) * page.page_size + page.items.length,
              total: page.total,
            })}
          </p>
          <div className="grid gap-6 lg:grid-cols-[1fr_1fr] lg:items-start">
            <ul className="space-y-3" aria-label="Polling units">
              {page.items.map((unit) => (
                <li key={unit.id}>
                  <PollingUnitCard unit={unit} selected={unit.id === selectedId} onShowOnMap={onSelect} />
                </li>
              ))}
            </ul>
            <div className="lg:sticky lg:top-20">
              <MapPanel units={page.items} selectedId={selectedId} onSelect={onSelect} />
            </div>
          </div>
          {page.total_pages > 1 && (
            <nav aria-label={t('Pagination')} className="flex items-center justify-between gap-3">
              <Button variant="outline" disabled={page.page <= 1} onClick={() => onPage(page.page - 1)}>
                {t('Previous')}
              </Button>
              <span className="text-sm text-muted-foreground">
                {t('Page {page} of {total}', { page: page.page, total: page.total_pages })}
              </span>
              <Button variant="outline" disabled={page.page >= page.total_pages} onClick={() => onPage(page.page + 1)}>
                {t('Next')}
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
