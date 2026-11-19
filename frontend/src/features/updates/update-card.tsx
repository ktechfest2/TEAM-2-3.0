import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/features/directory/data-notice'
import type { ElectionUpdate } from '@/features/directory/types'
import { UPDATE_CATEGORY_LABEL, UpdateVerificationBadge } from '@/features/updates/status'

export function UpdateCard({ update, headingLevel = 'h3' }: { update: ElectionUpdate; headingLevel?: 'h2' | 'h3' }) {
  const Heading = headingLevel
  return (
    <article aria-labelledby={`update-${update.id}`} className="rounded-lg border bg-card p-4">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline">{UPDATE_CATEGORY_LABEL[update.category]}</Badge>
        <UpdateVerificationBadge status={update.verification_status} />
      </div>
      <Heading id={`update-${update.id}`} className="mt-2 text-base font-semibold">
        <Link to={`/updates/${update.id}`} className="hover:underline">
          {update.title}
        </Link>
      </Heading>
      <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{update.description}</p>
      <p className="mt-2 text-xs text-muted-foreground">
        Source: <span className="font-medium text-foreground">{update.source_name}</span> · Published{' '}
        <time dateTime={update.published_at}>{formatDateTime(update.published_at)}</time>
      </p>
      {update.verification_status === 'reported_unverified' && (
        <p className="mt-1 text-xs font-medium text-warning">Not an official announcement.</p>
      )}
    </article>
  )
}
