import { ArrowLeftIcon, BadgeCheckIcon, CircleAlertIcon, MegaphoneIcon, UsersIcon } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { usePollingUnit } from '@/features/directory/api'
import { DataSourceNotice, formatDate, formatDateTime, FreshnessNote } from '@/features/directory/data-notice'
import type { OfficialNotice, PollingUnitDetail } from '@/features/directory/types'
import { MapPanel } from '@/features/polling-units/map-panel'
import { PollingUnitFacts } from '@/features/polling-units/polling-unit-card'
import {
  displayStatus,
  isOfficialNotice,
  POLLING_UNIT_STATUS_META,
  PollingUnitStatusBadge,
} from '@/features/polling-units/status'
import { ApiError } from '@/lib/api-client'

const NOTICE_KIND_LABEL: Record<OfficialNotice['kind'], string> = {
  relocation: 'Relocation notice',
  temporary_closure: 'Temporary closure notice',
}

function NoticeCard({ notice }: { notice: OfficialNotice }) {
  const official = isOfficialNotice(notice)
  return (
    <Alert variant={official ? 'info' : 'warning'}>
      {official ? <BadgeCheckIcon /> : <CircleAlertIcon />}
      <AlertTitle>
        {NOTICE_KIND_LABEL[notice.kind]}: {official ? 'officially confirmed' : 'Official confirmation unavailable.'}
      </AlertTitle>
      <AlertDescription>
        <dl className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
          <dt>Source</dt>
          <dd className="font-medium text-foreground">{notice.source_name ?? 'No authoritative source provided'}</dd>
          <dt>Reference</dt>
          <dd className="text-foreground">{notice.reference ?? 'Not provided'}</dd>
          {notice.new_location_description && (
            <>
              <dt>New location</dt>
              <dd className="text-foreground">{notice.new_location_description}</dd>
            </>
          )}
          <dt>Effective date</dt>
          <dd className="text-foreground">{formatDate(notice.effective_date)}</dd>
          <dt>Received by VoteTrace</dt>
          <dd className="text-foreground">{formatDateTime(notice.received_at)}</dd>
        </dl>
        {notice.source_url && (
          <a
            href={notice.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block font-medium text-navy underline"
          >
            View source document
          </a>
        )}
      </AlertDescription>
    </Alert>
  )
}

function NoticesSection({ unit }: { unit: PollingUnitDetail }) {
  const reports = unit.relocation_reports
  const hasOfficialRelocation = unit.official_notices.some((n) => n.kind === 'relocation' && isOfficialNotice(n))
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MegaphoneIcon className="size-4" aria-hidden />
          Notices and reports
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {unit.official_notices.length === 0 && !reports && (
          <p className="text-sm text-muted-foreground">No relocation or closure notices are recorded for this polling unit.</p>
        )}
        {unit.official_notices.map((notice) => (
          <NoticeCard key={notice.id} notice={notice} />
        ))}
        {reports && reports.report_count > 0 && (
          <Alert variant="warning">
            <UsersIcon />
            <AlertTitle>
              Relocation reported by the public ({reports.report_count}{' '}
              {reports.report_count === 1 ? 'report' : 'reports'})
            </AlertTitle>
            <AlertDescription>
              <p>
                These are unverified reports, not an official relocation notice and not an INEC announcement. Most recent
                report: {formatDateTime(reports.last_reported_at)}.
              </p>
              {!hasOfficialRelocation && <p className="mt-1 font-medium text-foreground">Official confirmation unavailable.</p>}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

export function PollingUnitDetailPage() {
  const { pollingUnitId } = useParams()
  const query = usePollingUnit(pollingUnitId)

  const back = (
    <Button asChild variant="ghost" size="sm" className="-ml-2">
      <Link to="/polling-units">
        <ArrowLeftIcon />
        Back to search
      </Link>
    </Button>
  )

  if (query.isPending) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        <h1 className="sr-only">Polling unit</h1>
        <LoadingState label="Loading polling unit" />
      </div>
    )
  }
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : undefined
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-10 sm:px-6">
        {back}
        <h1 className="text-2xl font-semibold">{status === 404 || status === 422 ? 'Polling unit not found' : 'Polling unit'}</h1>
        <ErrorState
          title={status === 404 || status === 422 ? 'Polling unit not found' : 'Could not load this polling unit'}
          message={
            status === 404 || status === 422
              ? 'Check the link, or search for the polling unit again.'
              : status === 0
                ? 'You are offline and this polling unit has not been saved on this device.'
                : 'Please try again.'
          }
          onRetry={status === 404 || status === 422 ? undefined : () => void query.refetch()}
        />
      </div>
    )
  }

  const { data, origin, syncedAt } = query.data
  const unit = data.item
  const status = displayStatus(unit)

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10 sm:px-6">
      {back}
      <PageHeader
        eyebrow="Polling unit"
        title={unit.name}
        description={`${unit.ward.name}, ${unit.lga.name}, ${unit.state.name}`}
        actions={
          <div className="flex flex-wrap gap-1.5">
            <PollingUnitStatusBadge status={status} />
          </div>
        }
      />
      <DataSourceNotice source={data.data_source} />
      <FreshnessNote result={{ origin, syncedAt }} />

      <Alert variant="default">
        <CircleAlertIcon />
        <AlertTitle>Status: {POLLING_UNIT_STATUS_META[status].label}</AlertTitle>
        <AlertDescription>{POLLING_UNIT_STATUS_META[status].description}</AlertDescription>
      </Alert>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <PollingUnitFacts unit={unit} />
          </CardContent>
        </Card>
        <NoticesSection unit={unit} />
      </div>

      <section aria-labelledby="map-heading" className="space-y-3">
        <h2 id="map-heading" className="text-lg font-semibold">
          Location
        </h2>
        <MapPanel units={[unit]} />
      </section>
    </div>
  )
}
