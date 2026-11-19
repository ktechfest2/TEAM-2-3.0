import { FileSearchIcon, InfoIcon, TriangleAlertIcon } from 'lucide-react'
import { Link } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select } from '@/components/ui/input'
import { usePublicIncidents } from '@/features/incidents/api'
import { BAND_DESCRIPTIONS, INCIDENT_CATEGORIES, type IncidentBand } from '@/features/incidents/types'
import { useSelectedElection } from '@/features/results/format'
import { useT } from '@/i18n/locale-provider'

const dateFormatter = new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium' })

/** Counts by public stage and reviewer-written summaries of verified incidents. Nothing else. */
export function PublicIncidentsPage() {
  const t = useT()
  const { query: elections, items, selected, select } = useSelectedElection()
  const summary = usePublicIncidents(selected?.id)

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t('Incident reporting')}
        title={t('Incident summary')}
        description={t('Reports received and how far review has got.')}
        actions={
          <Button asChild>
            <Link to="/report-incident">
              <TriangleAlertIcon />
              {t('Report an incident')}
            </Link>
          </Button>
        }
      />

      <Alert variant="info">
        <InfoIcon />
        <AlertTitle>{t('Reports are not findings')}</AlertTitle>
        <AlertDescription>
          {t('Counts include unchecked reports. Verified means reviewers confirmed it against evidence. No person or party is named.')}
        </AlertDescription>
      </Alert>

      {items.length > 1 && (
        <div className="max-w-sm space-y-1.5">
          <label htmlFor="public-incident-election" className="text-sm font-medium">
            {t('Election')}
          </label>
          <Select id="public-incident-election" value={selected?.id ?? ''} onChange={(e) => select(e.target.value)}>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </div>
      )}

      {elections.isPending || (selected && summary.isPending) ? (
        <LoadingState variant="skeleton" rows={3} label={t('Loading incident summary')} />
      ) : elections.isError || summary.isError ? (
        <ErrorState
          message={t('The incident summary could not be loaded. Check your connection and try again.')}
          onRetry={() => void (elections.isError ? elections.refetch() : summary.refetch())}
        />
      ) : !summary.data ? (
        <EmptyState icon={FileSearchIcon} title={t('No election configured')} description={t('There is no election to summarise yet.')} />
      ) : (
        <>
          <section aria-labelledby="band-heading" className="space-y-3">
            <h2 id="band-heading" className="text-lg font-semibold">
              {t('Reports by review stage')}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {summary.data.by_band.map((band) => (
                <div key={band.key} className="rounded-lg border bg-card p-4">
                  <p className="text-xs font-medium text-muted-foreground">{t(band.label)}</p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">{band.count.toLocaleString('en-NG')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t(BAND_DESCRIPTIONS[band.key as IncidentBand] ?? '')}</p>
                </div>
              ))}
            </div>
          </section>

          <section aria-labelledby="published-heading" className="space-y-3">
            <h2 id="published-heading" className="text-lg font-semibold">
              {t('Verified incidents')}
            </h2>
            {summary.data.published.length === 0 ? (
              <EmptyState
                icon={FileSearchIcon}
                title={t('No verified incidents published')}
                description={t('Summaries appear once reviewers verify an incident.')}
              />
            ) : (
              <ul className="space-y-3">
                {summary.data.published.map((item) => (
                  <li key={`${item.published_at}-${item.summary.slice(0, 20)}`}>
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">{t(INCIDENT_CATEGORIES[item.category])}</CardTitle>
                        <p className="text-xs text-muted-foreground">
                          {item.lga}, {item.state} · {dateFormatter.format(new Date(item.occurred_on))}
                        </p>
                      </CardHeader>
                      <CardContent className="text-sm">{item.summary}</CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <p className="text-xs text-muted-foreground">
            {t('Updated {time}', { time: new Date(summary.data.generated_at).toLocaleString('en-NG') })}
          </p>
        </>
      )}
    </div>
  )
}
