import { ArrowLeftIcon, CircleAlertIcon } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useUpdate } from '@/features/directory/api'
import { DataSourceNotice, formatDateTime, FreshnessNote } from '@/features/directory/data-notice'
import { UPDATE_CATEGORY_LABEL, UPDATE_VERIFICATION_META, UpdateVerificationBadge } from '@/features/updates/status'
import { ApiError } from '@/lib/api-client'

export function UpdateDetailPage() {
  const { updateId } = useParams()
  const query = useUpdate(updateId)

  const back = (
    <Button asChild variant="ghost" size="sm" className="-ml-2">
      <Link to="/updates">
        <ArrowLeftIcon />
        All updates
      </Link>
    </Button>
  )

  if (query.isPending) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <h1 className="sr-only">Election update</h1>
        <LoadingState label="Loading update" />
      </div>
    )
  }
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : undefined
    const missing = status === 404 || status === 422
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-10 sm:px-6">
        {back}
        <h1 className="text-2xl font-semibold">{missing ? 'Update not found' : 'Election update'}</h1>
        <ErrorState
          title={missing ? 'Update not found' : 'Could not load this update'}
          message={missing ? 'It may have been withdrawn, or the link is incorrect.' : 'Please try again.'}
          onRetry={missing ? undefined : () => void query.refetch()}
        />
      </div>
    )
  }

  const { data, origin, syncedAt } = query.data
  const update = data.item
  const meta = UPDATE_VERIFICATION_META[update.verification_status]

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-6">
      {back}
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline">{UPDATE_CATEGORY_LABEL[update.category]}</Badge>
        <UpdateVerificationBadge status={update.verification_status} />
      </div>
      <PageHeader title={update.title} description={`Published ${formatDateTime(update.published_at)}`} />
      <DataSourceNotice source={data.data_source} />
      <FreshnessNote result={{ origin, syncedAt }} />

      <Alert variant={meta.variant}>
        <meta.icon />
        <AlertTitle>{meta.label}</AlertTitle>
        <AlertDescription>{meta.description}</AlertDescription>
      </Alert>

      <Card>
        <CardContent className="space-y-4 pt-6">
          <p className="text-sm whitespace-pre-line">{update.description}</p>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-muted-foreground">Source</dt>
            <dd className="font-medium">{update.source_name}</dd>
            <dt className="text-muted-foreground">Reference</dt>
            <dd>{update.reference ?? 'Not provided'}</dd>
            <dt className="text-muted-foreground">Published</dt>
            <dd>{formatDateTime(update.published_at)}</dd>
          </dl>
          {update.source_url && (
            <a
              href={update.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-sm font-medium text-navy underline"
            >
              View original source
            </a>
          )}
          {update.polling_unit_id && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/polling-units/${update.polling_unit_id}`}>View the affected polling unit</Link>
            </Button>
          )}
        </CardContent>
      </Card>

      {update.verification_status !== 'officially_confirmed' && (
        <Alert variant="warning">
          <CircleAlertIcon />
          <AlertTitle>Not an INEC announcement</AlertTitle>
          <AlertDescription>
            Only updates marked "Officially confirmed" cite an authoritative source. Check official INEC channels before acting.
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}
