import { RefreshCwIcon, TriangleAlertIcon, WifiOffIcon } from 'lucide-react'
import { useT } from '@/i18n/locale-provider'
import { useOnlineStatus } from '@/lib/offline/use-online-status'
import { useSyncState } from '@/lib/offline/sync-engine'

export function OfflineBanner() {
  const t = useT()
  const online = useOnlineStatus()
  const sync = useSyncState()

  if (!online) {
    return (
      <div role="status" className="border-b border-warning/25 bg-warning-subtle">
        <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 text-sm text-foreground sm:px-6">
          <WifiOffIcon className="size-4 shrink-0 text-warning" aria-hidden />
          <span>
            {t(
              'You are offline. Information shown was saved on this device and may be out of date. New updates cannot be received until you reconnect.',
            )}
            {sync.pending > 0 &&
              ` ${t('{count} saved {pages} will refresh when you reconnect.', {
                count: sync.pending,
                pages: t(sync.pending === 1 ? 'page' : 'pages'),
              })}`}
          </span>
        </div>
      </div>
    )
  }

  if (sync.phase === 'syncing') {
    return (
      <div role="status" className="border-b bg-info-subtle">
        <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 text-sm sm:px-6">
          <RefreshCwIcon className="size-4 shrink-0 animate-spin text-info motion-reduce:animate-none" aria-hidden />
          <span>{t('Back online. Refreshing information saved on this device…')}</span>
        </div>
      </div>
    )
  }

  if (sync.phase === 'error' && sync.pending > 0) {
    return (
      <div role="status" className="border-b border-warning/25 bg-warning-subtle">
        <div className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 text-sm sm:px-6">
          <TriangleAlertIcon className="size-4 shrink-0 text-warning" aria-hidden />
          <span>{t('Some saved information could not be refreshed yet. It will be retried automatically.')}</span>
        </div>
      </div>
    )
  }

  return null
}
