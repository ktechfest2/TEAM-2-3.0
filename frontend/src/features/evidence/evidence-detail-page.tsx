import { ArrowLeftIcon, CalculatorIcon, ClipboardCheckIcon, ScanTextIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/input'
import { useAuth } from '@/features/auth/auth-context'
import { EVIDENCE_STAFF_ROLES, hasAnyRole } from '@/features/auth/roles'
import { formatDateTime } from '@/features/directory/data-notice'
import { AnomalyPanel, ComparisonPanel, ValidationPanel } from '@/features/evidence/analysis-panels'
import { useEvidence, useProcessEvidence, useReviewEvidence, useValidateEvidence } from '@/features/evidence/api'
import { EvidenceImageViewer } from '@/features/evidence/evidence-image-viewer'
import { ExtractionReview } from '@/features/evidence/extraction-review'
import { AuditTimeline, IntegrityPanel } from '@/features/evidence/integrity-panels'
import { EVIDENCE_STATUS_META, EvidenceStatusBadge } from '@/features/evidence/status'
import type { EvidenceDetail, ExtractedField, ReviewAction } from '@/features/evidence/types'
import { ApiError } from '@/lib/api-client'
import { cn } from '@/lib/utils'

type TabId = 'extraction' | 'validation' | 'comparison' | 'anomalies' | 'integrity' | 'audit'

const TABS: { id: TabId; label: string; staffOnly?: boolean }[] = [
  { id: 'extraction', label: 'Extracted result' },
  { id: 'validation', label: 'Arithmetic validation' },
  { id: 'comparison', label: 'Independent comparison', staffOnly: true },
  { id: 'anomalies', label: 'AI anomaly report', staffOnly: true },
  { id: 'integrity', label: 'Evidence integrity' },
  { id: 'audit', label: 'Audit timeline' },
]

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : 'The action could not be completed.'
}

function ReviewPanel({ evidence }: { evidence: EvidenceDetail }) {
  const review = useReviewEvidence(evidence.id)
  const [notes, setNotes] = useState('')
  const actions = evidence.allowed_actions
  const canDecide = actions.includes('approve')
  if (!canDecide && !actions.includes('start_review')) return null

  const run = (action: ReviewAction) =>
    review.mutate(
      { action, notes: notes.trim() || undefined },
      { onSuccess: () => setNotes('') },
    )

  return (
    <Card className="border-primary/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheckIcon className="size-4" aria-hidden /> Human review
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!canDecide ? (
          <>
            <p className="text-sm text-muted-foreground">
              Take this record into review to compare the original image with the extracted figures.
            </p>
            <Button onClick={() => run('start')} disabled={review.isPending}>
              Start review
            </Button>
          </>
        ) : (
          <>
            <label htmlFor="review-notes" className="text-sm font-medium">
              Reviewer notes
            </label>
            <Textarea
              id="review-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Required to reject, request a correction, or approve a flagged record."
              maxLength={4000}
            />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => run('approve')} disabled={review.isPending}>
                Approve figures
              </Button>
              <Button variant="outline" onClick={() => run('request_correction')} disabled={review.isPending}>
                Request correction
              </Button>
              <Button variant="destructive" onClick={() => run('reject')} disabled={review.isPending}>
                Reject evidence
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Approval needs current, passing validation and no unresolved fields. Verification requires independent
              approvals from different reviewers. You cannot review your own submission.
            </p>
          </>
        )}
        {review.isError && (
          <p role="alert" className="text-sm font-medium text-destructive">
            {errorMessage(review.error)}
          </p>
        )}
        {review.data && (
          <p role="status" className="text-sm text-muted-foreground">
            Recorded. Approvals on the current figures: {review.data.approvals} of {review.data.approvals_required}.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function ActionBar({ evidence }: { evidence: EvidenceDetail }) {
  const process = useProcessEvidence(evidence.id)
  const validate = useValidateEvidence(evidence.id)
  const actions = evidence.allowed_actions
  const error = process.error ?? validate.error
  if (!actions.includes('process') && !actions.includes('validate')) return null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {actions.includes('process') && (
          <Button
            variant={evidence.status === 'received' ? 'default' : 'outline'}
            onClick={() => process.mutate()}
            disabled={process.isPending}
          >
            <ScanTextIcon />
            {process.isPending ? 'Processing…' : evidence.status === 'received' ? 'Run OCR processing' : 'Reprocess image'}
          </Button>
        )}
        {actions.includes('validate') && (
          <Button onClick={() => validate.mutate()} disabled={validate.isPending}>
            <CalculatorIcon />
            {validate.isPending ? 'Checking…' : 'Validate and cross-check'}
          </Button>
        )}
      </div>
      {process.isPending && (
        <p role="status" className="text-sm text-muted-foreground">
          Verifying the original’s fingerprint, correcting orientation, enhancing contrast and reading text…
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {errorMessage(error)}
        </p>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{title}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  )
}

export function EvidenceDetailPage({ backTo, backLabel }: { backTo: string; backLabel: string }) {
  const { submissionId = '' } = useParams()
  const { user } = useAuth()
  const isStaff = hasAnyRole(user?.roles ?? [], EVIDENCE_STAFF_ROLES)
  const evidence = useEvidence(submissionId)
  const [tab, setTab] = useState<TabId>('extraction')
  const [selected, setSelected] = useState<ExtractedField | null>(null)

  if (evidence.isPending) return <LoadingState label="Loading evidence" />
  if (evidence.isError) {
    return (
      <ErrorState
        title={evidence.error instanceof ApiError && evidence.error.status === 404 ? 'Evidence not found' : undefined}
        message={errorMessage(evidence.error)}
        onRetry={() => void evidence.refetch()}
      />
    )
  }
  const item = evidence.data
  const tabs = TABS.filter((entry) => !entry.staffOnly || isStaff)
  const meta = EVIDENCE_STATUS_META[item.status]

  return (
    <div className="space-y-6">
      <Button asChild variant="link" className="gap-1">
        <Link to={backTo}>
          <ArrowLeftIcon /> {backLabel}
        </Link>
      </Button>
      <PageHeader
        eyebrow="Evidence submission"
        title={`${item.polling_unit.code} · ${item.polling_unit.name}`}
        description={`${item.election.name}${item.polling_unit.ward ? ` · ${item.polling_unit.ward}, ${item.polling_unit.lga}, ${item.polling_unit.state}` : ''}`}
        actions={<EvidenceStatusBadge status={item.status} />}
      />
      <Alert variant={meta.tone === 'neutral' ? 'default' : meta.tone}>
        <meta.icon />
        <AlertTitle>{meta.label}</AlertTitle>
        <AlertDescription>
          {meta.description} {item.status_notice}
        </AlertDescription>
      </Alert>
      {item.processing_error && (
        <p role="alert" className="text-sm text-destructive">
          Last processing attempt failed ({item.processing_error.replaceAll('_', ' ')}).
        </p>
      )}

      <ActionBar evidence={item} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="space-y-4">
          <EvidenceImageViewer submissionId={item.id} images={item.images} highlight={selected} />
          <dl className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
            <Section title="Received by server">{formatDateTime(item.received_at)}</Section>
            <Section title="Captured (device time)">{formatDateTime(item.captured_at)}</Section>
            <Section title="Status changed">{formatDateTime(item.status_changed_at)}</Section>
            <Section title="Submitted by">{item.is_mine ? 'You' : item.submitted_by ? `Account ${item.submitted_by.slice(0, 8)}` : 'Not recorded'}</Section>
          </dl>
          <ReviewPanel evidence={item} />
        </div>

        <div className="min-w-0 space-y-4">
          <div role="tablist" aria-label="Evidence details" className="flex gap-1 overflow-x-auto border-b">
            {tabs.map((entry) => (
              <button
                key={entry.id}
                role="tab"
                type="button"
                id={`tab-${entry.id}`}
                aria-selected={tab === entry.id}
                aria-controls={`panel-${entry.id}`}
                onClick={() => setTab(entry.id)}
                className={cn(
                  '-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                  tab === entry.id
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {entry.label}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'extraction' && (
              <ExtractionReview
                submissionId={item.id}
                canCorrect={item.allowed_actions.includes('correct')}
                onSelectField={setSelected}
                selectedKey={selected?.field_key ?? null}
              />
            )}
            {tab === 'validation' && <ValidationPanel submissionId={item.id} />}
            {tab === 'comparison' && <ComparisonPanel submissionId={item.id} />}
            {tab === 'anomalies' && <AnomalyPanel submissionId={item.id} />}
            {tab === 'integrity' && <IntegrityPanel submissionId={item.id} />}
            {tab === 'audit' && <AuditTimeline submissionId={item.id} />}
          </div>
        </div>
      </div>
    </div>
  )
}
