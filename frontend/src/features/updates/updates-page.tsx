import { MegaphoneIcon } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { describedBy, FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { useUpdates } from '@/features/directory/api'
import { DataSourceNotice, FreshnessNote } from '@/features/directory/data-notice'
import {
  UPDATE_CATEGORIES,
  UPDATE_VERIFICATION_STATUSES,
  type UpdateCategory,
  type UpdateVerificationStatus,
} from '@/features/directory/types'
import { UPDATE_CATEGORY_LABEL, UPDATE_VERIFICATION_META, UpdateVerificationBadge } from '@/features/updates/status'
import { UpdateCard } from '@/features/updates/update-card'
import { useT } from '@/i18n/locale-provider'
import { ApiError } from '@/lib/api-client'

const PAGE_SIZE = 10
const DATE = /^\d{4}-\d{2}-\d{2}$/

function oneOf<T extends string>(values: readonly T[], value: string | null): T | undefined {
  return values.find((candidate) => candidate === value)
}

function validDate(value: string | null) {
  return value && DATE.test(value) && !Number.isNaN(Date.parse(value)) ? value : undefined
}

/** Local calendar day boundaries, sent to the API as UTC instants. */
function startOfDay(day: string) {
  return new Date(`${day}T00:00:00`).toISOString()
}
function endOfDay(day: string) {
  return new Date(`${day}T23:59:59.999`).toISOString()
}

export function UpdatesPage() {
  const t = useT()
  const [params, setParams] = useSearchParams()
  const category = oneOf(UPDATE_CATEGORIES, params.get('category'))
  const verification = oneOf(UPDATE_VERIFICATION_STATUSES, params.get('verification'))
  const from = validDate(params.get('from'))
  const to = validDate(params.get('to'))
  const page = Math.max(1, Number(params.get('page')) || 1)
  const rangeError = from && to && from > to ? 'The start date must be on or before the end date.' : undefined

  const updates = useUpdates(
    {
      category,
      verificationStatus: verification,
      publishedFrom: from ? startOfDay(from) : undefined,
      publishedTo: to ? endOfDay(to) : undefined,
      page,
      pageSize: PAGE_SIZE,
    },
    !rangeError,
  )

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  const hasFilters = Boolean(category || verification || from || to)

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-10 sm:px-6">
      <PageHeader
        title={t('Election updates')} description={t('Notices on polling units, schedules and security, each with its source.')}
      />

      <Card>
        <CardContent className="pt-6">
          <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label={t('Filter updates')} onSubmit={(e) => e.preventDefault()}>
            <FormField id="update-category" label={t('Category')}>
              <Select id="update-category" value={category ?? ''} onChange={(e) => setFilter('category', e.target.value)}>
                <option value="">{t('All categories')}</option>
                {UPDATE_CATEGORIES.map((value) => (
                  <option key={value} value={value}>
                    {t(UPDATE_CATEGORY_LABEL[value as UpdateCategory])}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="update-verification" label="Verification">
              <Select
                id="update-verification"
                value={verification ?? ''}
                onChange={(e) => setFilter('verification', e.target.value)}
              >
                <option value="">Any verification status</option>
                {UPDATE_VERIFICATION_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {UPDATE_VERIFICATION_META[value as UpdateVerificationStatus].label}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField id="update-from" label="From date" error={rangeError}>
              <Input
                id="update-from"
                type="date"
                value={from ?? ''}
                aria-invalid={Boolean(rangeError)}
                aria-describedby={describedBy('update-from', rangeError)}
                onChange={(e) => setFilter('from', e.target.value)}
              />
            </FormField>
            <FormField id="update-to" label="To date">
              <Input
                id="update-to"
                type="date"
                value={to ?? ''}
                aria-invalid={Boolean(rangeError)}
                onChange={(e) => setFilter('to', e.target.value)}
              />
            </FormField>
            {hasFilters && (
              <div className="sm:col-span-2 lg:col-span-4">
                <Button type="button" variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams())}>
                  Clear filters
                </Button>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      <details className="rounded-lg border bg-surface px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">What the verification labels mean</summary>
        <dl className="mt-3 space-y-3">
          {UPDATE_VERIFICATION_STATUSES.map((value) => (
            <div key={value}>
              <dt>
                <UpdateVerificationBadge status={value} />
              </dt>
              <dd className="mt-1 text-muted-foreground">{UPDATE_VERIFICATION_META[value].description}</dd>
            </div>
          ))}
        </dl>
      </details>

      <section aria-labelledby="updates-heading" className="space-y-4">
        <h2 id="updates-heading" className="text-lg font-semibold">
          Updates
        </h2>
        {rangeError ? (
          <EmptyState icon={MegaphoneIcon} title="Adjust the date range" description={rangeError} />
        ) : updates.isPending ? (
          <LoadingState variant="skeleton" rows={3} label="Loading updates" />
        ) : updates.isError ? (
          <ErrorState
            message={
              updates.error instanceof ApiError && updates.error.status === 0
                ? 'You are offline and these updates have not been saved on this device.'
                : 'Updates could not be loaded. Please try again.'
            }
            onRetry={() => void updates.refetch()}
          />
        ) : (
          <>
            <DataSourceNotice source={updates.data.data.data_source} />
            <FreshnessNote result={updates.data} />
            {updates.data.data.items.length === 0 ? (
              <EmptyState
                icon={MegaphoneIcon}
                title="No updates found"
                description={hasFilters ? 'No updates match these filters.' : 'No election updates have been published yet.'}
              />
            ) : (
              <ul className="space-y-3" aria-label="Election updates">
                {updates.data.data.items.map((update) => (
                  <li key={update.id}>
                    <UpdateCard update={update} />
                  </li>
                ))}
              </ul>
            )}
            {updates.data.data.total_pages > 1 && (
              <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
                <Button variant="outline" disabled={page <= 1} onClick={() => setFilter('page', String(page - 1))}>
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {updates.data.data.page} of {updates.data.data.total_pages}
                </span>
                <Button
                  variant="outline"
                  disabled={page >= updates.data.data.total_pages}
                  onClick={() => setFilter('page', String(page + 1))}
                >
                  Next
                </Button>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  )
}
