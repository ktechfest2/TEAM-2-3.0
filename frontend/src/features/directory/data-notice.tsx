import { HistoryIcon, InfoIcon } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import type { DataSource } from '@/features/directory/types'
import type { CachedResult } from '@/lib/offline/public-cache'

const dateTime = new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium', timeStyle: 'short' })
const dateOnly = new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium' })

export function formatDateTime(value: string | null | undefined) {
  return value ? dateTime.format(new Date(value)) : 'Not available'
}

export function formatDate(value: string | null | undefined) {
  return value ? dateOnly.format(new Date(`${value.slice(0, 10)}T00:00:00`)) : 'Not available'
}

/** Polling-unit locations guide voters, so a sample directory stays labelled, quietly. */
export function DataSourceNotice({ source }: { source: DataSource }) {
  if (source.kind !== 'demo') return null
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <InfoIcon className="size-4 shrink-0" aria-hidden />
      Sample directory, not sourced from INEC.
    </p>
  )
}

/** Tells the user whether they are looking at live or device-saved data. */
export function FreshnessNote({ result }: { result: Pick<CachedResult<unknown>, 'origin' | 'syncedAt'> }) {
  if (result.origin === 'cache') {
    return (
      <Alert variant="warning">
        <HistoryIcon />
        <AlertTitle>Saved copy from {formatDateTime(result.syncedAt)}</AlertTitle>
        <AlertDescription>The server could not be reached, so this may be out of date.</AlertDescription>
      </Alert>
    )
  }
  return <p className="text-xs text-muted-foreground">Last synced {formatDateTime(result.syncedAt)}</p>
}
