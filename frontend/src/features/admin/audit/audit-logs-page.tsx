import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2Icon, ScrollTextIcon, ShieldAlertIcon } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { FormField } from '@/components/forms/form-field'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useT } from '@/i18n/locale-provider'
import { api, ApiError } from '@/lib/api-client'

type AuditEvent = {
  id: string
  created_at: string
  action: string
  entity_type: string
  entity_id: string
  sequence: number
  actor_type: string
  actor_id: string | null
  actor_email: string | null
  request_id: string | null
  details: Record<string, unknown>
  event_hash: string
}

type AuditPage = {
  items: AuditEvent[]
  total: number
  page: number
  page_size: number
  entity_types: string[]
}

type ChainResult = { valid: boolean; events: number; broken_at_sequence: number | null; problem: string | null }

const PAGE_SIZE = 25

function ChainCheck({ event }: { event: AuditEvent }) {
  const t = useT()
  const check = useMutation({
    mutationFn: () =>
      api.get<ChainResult>(`/admin/audit-events/chains/${encodeURIComponent(event.entity_type)}/${event.entity_id}`),
  })
  if (check.data) {
    return check.data.valid ? (
      <Badge variant="success">
        <CheckCircle2Icon className="size-3" aria-hidden />
        {t('Chain intact ({count} events)', { count: check.data.events })}
      </Badge>
    ) : (
      <Badge variant="destructive">
        <ShieldAlertIcon className="size-3" aria-hidden />
        {t('Chain broken at event {sequence}', { sequence: check.data.broken_at_sequence ?? '?' })}
      </Badge>
    )
  }
  return (
    <Button type="button" size="sm" variant="outline" disabled={check.isPending} onClick={() => check.mutate()}>
      {check.isPending && <Spinner />}
      {check.isError ? t('Retry check') : t('Verify chain')}
    </Button>
  )
}

export function AuditLogsPage() {
  const t = useT()
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
  if (entityType) params.set('entity_type', entityType)
  if (action.trim()) params.set('action', action.trim())

  const events = useQuery({
    queryKey: ['admin', 'audit', entityType, action.trim(), page],
    queryFn: () => api.get<AuditPage>(`/admin/audit-events?${params.toString()}`),
    placeholderData: keepPreviousData,
  })
  const totalPages = events.data ? Math.max(1, Math.ceil(events.data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Audit logs')}
        description={t('Security and verification actions, newest first. Records are hash-chained.')}
      />
      <Card>
        <CardContent className="grid gap-4 pt-6 sm:grid-cols-3">
          <FormField id="audit-entity" label={t('Record type')}>
            <Select
              id="audit-entity"
              value={entityType}
              onChange={(event) => {
                setEntityType(event.target.value)
                setPage(1)
              }}
            >
              <option value="">{t('All record types')}</option>
              {(events.data?.entity_types ?? []).map((type) => (
                <option key={type} value={type}>
                  {type.replaceAll('_', ' ')}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="audit-action" label={t('Action starts with')}>
            <Input
              id="audit-action"
              placeholder="account."
              value={action}
              onChange={(event) => {
                setAction(event.target.value)
                setPage(1)
              }}
            />
          </FormField>
          <div className="flex items-end">
            <Button
              type="button"
              variant="outline"
              disabled={!entityType && !action}
              onClick={() => {
                setEntityType('')
                setAction('')
                setPage(1)
              }}
            >
              {t('Clear filters')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {events.isPending ? (
        <LoadingState />
      ) : events.isError ? (
        <ErrorState
          message={events.error instanceof ApiError ? events.error.message : undefined}
          onRetry={() => void events.refetch()}
        />
      ) : events.data.items.length === 0 ? (
        <EmptyState
          icon={ScrollTextIcon}
          title={t('No audit events')}
          description={t('Nothing matches these filters.')}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y">
              {events.data.items.map((event) => (
                <li key={event.id} className="space-y-2 px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="font-mono font-semibold">{event.action}</code>
                      <Badge variant="neutral">{event.entity_type.replaceAll('_', ' ')}</Badge>
                      <span className="text-muted-foreground">#{event.sequence}</span>
                    </div>
                    <time className="text-muted-foreground" dateTime={event.created_at}>
                      {new Date(event.created_at).toLocaleString()}
                    </time>
                  </div>
                  <p className="text-muted-foreground">
                    {event.actor_type === 'system'
                      ? t('By the system')
                      : t('By {actor}', { actor: event.actor_email ?? event.actor_id ?? t('unknown user') })}
                    {' · '}
                    <span className="font-mono text-xs">{event.entity_id}</span>
                  </p>
                  {Object.keys(event.details).length > 0 && (
                    <pre className="overflow-x-auto rounded bg-muted/50 p-2 font-mono text-xs">
                      {JSON.stringify(event.details, null, 2)}
                    </pre>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-mono text-xs text-muted-foreground" title={event.event_hash}>
                      {t('Hash')} {event.event_hash.slice(0, 16)}…
                    </span>
                    <ChainCheck event={event} />
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {events.data && events.data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="text-muted-foreground">
            {t('Page {page} of {pages} · {total} events', { page, pages: totalPages, total: events.data.total })}
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              {t('Previous')}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              {t('Next')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
