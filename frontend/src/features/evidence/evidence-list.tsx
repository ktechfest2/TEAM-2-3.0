import { ChevronRightIcon } from 'lucide-react'
import { Link } from 'react-router'
import { formatDateTime } from '@/features/directory/data-notice'
import { EvidenceStatusBadge } from '@/features/evidence/status'
import type { EvidenceSummary } from '@/features/evidence/types'

type EvidenceListProps = {
  items: EvidenceSummary[]
  basePath: string
  notice?: string
}

export function EvidenceList({ items, basePath, notice }: EvidenceListProps) {
  return (
    <div className="space-y-2">
      <ul className="divide-y rounded-lg border bg-card">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={`${basePath}/${item.id}`}
              className="flex items-center gap-3 p-4 transition-colors hover:bg-muted focus-visible:bg-muted"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <p className="font-medium">
                  {item.polling_unit.code} · {item.polling_unit.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {item.election.name}
                  {item.polling_unit.ward && ` · ${item.polling_unit.ward}, ${item.polling_unit.lga}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  Received {formatDateTime(item.received_at)}
                  {item.captured_at && ` · captured ${formatDateTime(item.captured_at)}`}
                </p>
              </div>
              <EvidenceStatusBadge status={item.status} />
              <ChevronRightIcon className="size-4 text-muted-foreground" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
      {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
    </div>
  )
}
