import { CheckCircle2Icon, LinkIcon, ShieldAlertIcon, ShieldCheckIcon } from 'lucide-react'
import { ErrorState, LoadingState } from '@/components/feedback/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/features/directory/data-notice'
import { useAudit, useIntegrity } from '@/features/evidence/api'

const ACTION_LABELS: Record<string, string> = {
  'evidence.received': 'Evidence received',
  'evidence.hashed': 'Original fingerprinted (SHA-256)',
  'evidence.integrity_verified': 'Original re-verified',
  'evidence.integrity_failed': 'Integrity check FAILED',
  'ocr.started': 'OCR started',
  'ocr.completed': 'OCR completed',
  'ocr.failed': 'OCR failed',
  'extraction.corrected': 'Values corrected by a person',
  'validation.completed': 'Arithmetic validation run',
  'comparison.completed': 'Compared with other submissions',
  'anomaly.detected': 'AI anomaly flagged',
  'review.recorded': 'Human review action',
  'status.changed': 'Status changed',
}

function Hash({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs break-all">{value ?? 'Not recorded'}</dd>
    </div>
  )
}

export function IntegrityPanel({ submissionId }: { submissionId: string }) {
  const integrity = useIntegrity(submissionId, true)
  if (integrity.isPending) return <LoadingState label="Re-verifying evidence" />
  if (integrity.isError) return <ErrorState onRetry={() => void integrity.refetch()} />
  const data = integrity.data
  const ok = data.original_verified && data.audit_chain_valid
  return (
    <div className="space-y-4">
      <Alert variant={ok ? 'success' : 'destructive'}>
        {ok ? <ShieldCheckIcon /> : <ShieldAlertIcon />}
        <AlertTitle>
          {data.original_verified ? 'Stored original matches its fingerprint' : 'Stored original does NOT match its fingerprint'}
        </AlertTitle>
        <AlertDescription>
          Checked {formatDateTime(data.checked_at)}. Audit chain {data.audit_chain_valid ? 'intact' : 'broken'} (
          {data.audit_chain_length} events).
        </AlertDescription>
      </Alert>
      <dl className="grid gap-3">
        <Hash label="Original image SHA-256 (exact uploaded bytes)" value={data.original_sha256} />
        <Hash label="Current result fingerprint (canonical figures)" value={data.current_result_hash} />
        <Hash label="Result fingerprint at last validation" value={data.validated_result_hash} />
        <Hash label="Audit chain head (hash of the latest event)" value={data.audit_head_hash} />
      </dl>
      {data.result_hash_matches_validation === false && (
        <p className="text-sm text-warning">The figures changed after the last validation.</p>
      )}
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Captured on device (reported by device)</dt>
          <dd>{formatDateTime(data.captured_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Received by server</dt>
          <dd>{formatDateTime(data.received_at)}</dd>
        </div>
      </dl>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {Object.entries(data.hash_notes).map(([key, note]) => (
          <li key={key}>{note}</li>
        ))}
      </ul>
    </div>
  )
}

export function AuditTimeline({ submissionId }: { submissionId: string }) {
  const audit = useAudit(submissionId)
  if (audit.isPending) return <LoadingState label="Loading audit trail" />
  if (audit.isError) return <ErrorState onRetry={() => void audit.refetch()} />
  const data = audit.data
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {data.chain_valid ? (
          <Badge variant="success">
            <CheckCircle2Icon aria-hidden /> Hash chain intact
          </Badge>
        ) : (
          <Badge variant="destructive">
            <ShieldAlertIcon aria-hidden /> Chain broken at event {data.broken_at_sequence} ({data.problem})
          </Badge>
        )}
        <span className="text-muted-foreground">{data.events.length} events</span>
      </div>
      <ol className="relative space-y-4 border-l pl-5">
        {data.events.map((event) => (
          <li key={event.id} className="relative">
            <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full bg-primary" aria-hidden />
            <p className="text-sm font-medium">
              {ACTION_LABELS[event.action] ?? event.action}
              {event.action === 'status.changed' && typeof event.details.to === 'string' && (
                <span className="font-normal text-muted-foreground"> → {event.details.to.replaceAll('_', ' ')}</span>
              )}
              {event.action === 'review.recorded' && typeof event.details.decision === 'string' && (
                <span className="font-normal text-muted-foreground"> · {event.details.decision.replaceAll('_', ' ')}</span>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              #{event.sequence} · {formatDateTime(event.created_at)} · by {event.actor}
            </p>
            <details className="mt-1 text-xs">
              <summary className="cursor-pointer text-navy">Details and hashes</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 whitespace-pre-wrap">
                {JSON.stringify(event.details, null, 2)}
              </pre>
              <p className="mt-1 flex items-start gap-1 font-mono break-all text-muted-foreground">
                <LinkIcon className="mt-0.5 size-3 shrink-0" aria-hidden />
                prev {event.previous_hash.slice(0, 16)}… → {event.event_hash.slice(0, 16)}…
              </p>
            </details>
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted-foreground">{data.notice}</p>
    </div>
  )
}
