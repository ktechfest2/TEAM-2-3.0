import { FileStackIcon } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/input'
import { useEvidenceList, type EvidenceListFilters } from '@/features/evidence/api'
import { EvidenceList } from '@/features/evidence/evidence-list'
import { EVIDENCE_STATUS_META } from '@/features/evidence/status'
import { EVIDENCE_STATUSES, type EvidenceStatus } from '@/features/evidence/types'
import { useT } from '@/i18n/locale-provider'

function Pager({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (page: number) => void }) {
  if (totalPages <= 1) return null
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <span>
        Page {page} of {totalPages}
      </span>
      <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </nav>
  )
}

function Listing({ filters, emptyTitle, emptyDescription }: { filters: EvidenceListFilters; emptyTitle: string; emptyDescription: string }) {
  const [page, setPage] = useState(1)
  const list = useEvidenceList({ ...filters, page })
  if (list.isPending) return <LoadingState variant="skeleton" label="Loading submissions" />
  if (list.isError) return <ErrorState onRetry={() => void list.refetch()} />
  if (list.data.items.length === 0) {
    return <EmptyState icon={FileStackIcon} title={emptyTitle} description={emptyDescription} />
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{list.data.total} submission(s)</p>
      <EvidenceList items={list.data.items} basePath="/admin/evidence" />
      <Pager page={list.data.page} totalPages={list.data.total_pages} onPage={setPage} />
    </div>
  )
}

export function EvidenceSubmissionsPage() {
  const t = useT()
  const [status, setStatus] = useState<EvidenceStatus | ''>('')
  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Evidence submissions')}
        description={t('Result-sheet photos and their review state.')}
      />
      <div className="max-w-xs space-y-1.5">
        <label htmlFor="evidence-status-filter" className="text-sm font-medium">
          {t('Status')}
        </label>
        <Select
          id="evidence-status-filter"
          value={status}
          onChange={(event) => setStatus(event.target.value as EvidenceStatus | '')}
        >
          <option value="">{t('All statuses')}</option>
          {EVIDENCE_STATUSES.map((value) => (
            <option key={value} value={value}>
              {EVIDENCE_STATUS_META[value].label}
            </option>
          ))}
        </Select>
      </div>
      <Listing
        key={status}
        filters={{ status: status || undefined }}
        emptyTitle={t('No evidence submitted')}
        emptyDescription={t('Submissions from field observers and party agents appear here once uploaded.')}
      />
    </div>
  )
}

export function VerificationReviewPage() {
  const t = useT()
  return (
    <div className="space-y-6">
      <PageHeader title={t('Verification review')} description={t('Oldest records first.')} />
      <Listing
        filters={{ queue: 'review' }}
        emptyTitle="Review queue is empty"
        emptyDescription="Records appear here after validation and cross-checking."
      />
    </div>
  )
}
