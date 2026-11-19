import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CameraIcon,
  CheckCircle2Icon,
  CloudOffIcon,
  CloudUploadIcon,
  RefreshCwIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/features/directory/data-notice'
import { EVIDENCE_KEY, useEvidenceList } from '@/features/evidence/api'
import {
  discardDraft,
  listDrafts,
  retryDraft,
  syncEvidence,
  useEvidenceSyncState,
} from '@/features/evidence/evidence-queue'
import { EvidenceList } from '@/features/evidence/evidence-list'
import { formatBytes } from '@/features/evidence/file-checks'
import type { EvidenceDraft } from '@/lib/offline/db'
import { useT } from '@/i18n/locale-provider'
import { useOnlineStatus } from '@/lib/offline/use-online-status'

const DRAFTS_KEY = ['device', 'evidence-drafts']

function DraftStatus({ draft, active }: { draft: EvidenceDraft; active: boolean }) {
  if (draft.uploadStatus === 'confirmed') {
    return (
      <Badge variant="success">
        <CheckCircle2Icon aria-hidden />
        Received by server
      </Badge>
    )
  }
  if (draft.uploadStatus === 'uploading' && active) {
    return (
      <Badge variant="info">
        <CloudUploadIcon aria-hidden />
        Uploading…
      </Badge>
    )
  }
  if (draft.uploadStatus === 'failed') {
    return (
      <Badge variant="destructive">
        <TriangleAlertIcon aria-hidden />
        Not accepted
      </Badge>
    )
  }
  return (
    <Badge variant="neutral">
      <CloudOffIcon aria-hidden />
      Waiting to upload · not yet received
    </Badge>
  )
}

export function MyEvidencePage() {
  const t = useT()
  const queryClient = useQueryClient()
  const online = useOnlineStatus()
  const sync = useEvidenceSyncState()
  const location = useLocation()
  const justSaved = (location.state as { saved?: boolean } | null)?.saved

  const drafts = useQuery({
    queryKey: [...DRAFTS_KEY, sync.completed, sync.running],
    queryFn: () => listDrafts(),
  })
  const server = useEvidenceList({ mine: true })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: DRAFTS_KEY })
    void queryClient.invalidateQueries({ queryKey: [EVIDENCE_KEY] })
  }
  const uploadNow = async () => {
    await syncEvidence()
    refresh()
  }

  const unconfirmed = (drafts.data ?? []).filter((draft) => draft.uploadStatus !== 'confirmed')
  const confirmed = (drafts.data ?? []).filter((draft) => draft.uploadStatus === 'confirmed')

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t('Field evidence')}
        title={t('My submissions')}
        description={t('Photos on this device and submissions we have received.')}
        actions={
          <Button asChild>
            <Link to="/evidence/submit">
              <CameraIcon />
              {t('Submit evidence')}
            </Link>
          </Button>
        }
      />

      {justSaved && (
        <Alert variant="info">
          <CloudUploadIcon />
          <AlertTitle>Saved on this device</AlertTitle>
          <AlertDescription>
            {online
              ? 'Uploading now. It counts as received only when the server confirms it below.'
              : 'You are offline. It will upload automatically when you reconnect.'}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>On this device</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void uploadNow()}
            disabled={!online || sync.running || unconfirmed.length === 0}
          >
            <RefreshCwIcon />
            Upload now
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {sync.running && (
            <div role="status" className="space-y-1">
              <p className="text-sm">
                Uploading {Math.min(sync.completed + 1, sync.total)} of {sync.total}…
              </p>
              <progress
                className="h-2 w-full overflow-hidden rounded-full accent-primary"
                max={sync.total}
                value={sync.completed}
                aria-label="Upload progress"
              />
            </div>
          )}
          {drafts.isPending ? (
            <LoadingState label="Reading saved photos" />
          ) : unconfirmed.length === 0 ? (
            <p className="text-sm text-muted-foreground">No photos are waiting to upload.</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {unconfirmed.map((draft) => (
                <li key={draft.localId} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {draft.pollingUnitCode} · {draft.pollingUnitName}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {draft.electionName} · captured {formatDateTime(draft.capturedAt)} · {formatBytes(draft.byteSize)}
                    </p>
                    {draft.lastError && <p className="text-xs text-destructive">{draft.lastError}</p>}
                  </div>
                  <DraftStatus draft={draft} active={sync.currentId === draft.localId} />
                  <div className="flex gap-1">
                    {draft.uploadStatus === 'failed' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void retryDraft(draft.localId).then(uploadNow)}
                        disabled={!online}
                      >
                        Retry
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete saved photo for ${draft.pollingUnitCode}`}
                      onClick={() => {
                        if (window.confirm('Delete this photo from the device? It has not been received by the server.')) {
                          void discardDraft(draft.localId).then(refresh)
                        }
                      }}
                    >
                      <Trash2Icon />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {confirmed.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {confirmed.length} photo{confirmed.length === 1 ? ' was' : 's were'} confirmed by the server and removed
              from device storage.
            </p>
          )}
        </CardContent>
      </Card>

      <section aria-labelledby="received-heading" className="space-y-3">
        <h2 id="received-heading" className="text-lg font-semibold">
          Received by VoteTrace
        </h2>
        {server.isPending ? (
          <LoadingState variant="skeleton" label="Loading your submissions" />
        ) : server.isError ? (
          <ErrorState
            message={online ? 'Your submissions could not be loaded.' : 'Reconnect to see submissions on the server.'}
            onRetry={() => void server.refetch()}
          />
        ) : server.data.items.length === 0 ? (
          <EmptyState title="No submissions received yet" description="Confirmed uploads will appear here." />
        ) : (
          <EvidenceList items={server.data.items} basePath="/evidence" notice={server.data.status_notice} />
        )}
      </section>
    </div>
  )
}
