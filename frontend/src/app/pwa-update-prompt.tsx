import { RefreshCwIcon } from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { Button } from '@/components/ui/button'

/**
 * Asks before activating a new service worker so an update never reloads
 * the page while someone is filling in a form.
 */
export function PwaUpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  if (!needRefresh) return null

  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md items-center gap-3 rounded-lg border bg-card p-4 shadow-lg"
    >
      <RefreshCwIcon className="size-4 shrink-0 text-primary" aria-hidden />
      <p className="flex-1 text-sm">A new version of VoteTrace is available.</p>
      <Button size="sm" variant="ghost" onClick={() => setNeedRefresh(false)}>
        Later
      </Button>
      <Button size="sm" onClick={() => void updateServiceWorker(true)}>
        Update
      </Button>
    </div>
  )
}
