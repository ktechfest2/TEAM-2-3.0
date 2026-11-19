import { CheckIcon, HistoryIcon, PencilIcon, ScanTextIcon, TriangleAlertIcon } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDateTime } from '@/features/directory/data-notice'
import { useCorrectExtraction, useExtraction } from '@/features/evidence/api'
import { confidenceTone, formatConfidence, reviewReasonLabel } from '@/features/evidence/status'
import type { ExtractedField, FieldCorrection } from '@/features/evidence/types'
import { ApiError } from '@/lib/api-client'

type Draft = { value: string; reason: string }

function display(value: ExtractedField['value']) {
  return value === null || value === '' ? 'Not recorded' : String(value)
}

function parseValue(field: ExtractedField, raw: string): FieldCorrection['value'] | 'invalid' {
  const trimmed = raw.trim()
  if (trimmed === '') return null
  if (field.kind === 'text') return trimmed
  return /^\d+$/.test(trimmed) ? Number(trimmed) : 'invalid'
}

type ExtractionReviewProps = {
  submissionId: string
  canCorrect: boolean
  onSelectField: (field: ExtractedField | null) => void
  selectedKey: string | null
}

export function ExtractionReview({ submissionId, canCorrect, onSelectField, selectedKey }: ExtractionReviewProps) {
  const extraction = useExtraction(submissionId)
  const correct = useCorrectExtraction(submissionId)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [error, setError] = useState<string>()
  const [historyFor, setHistoryFor] = useState<string | null>(null)

  if (extraction.isPending) return <LoadingState label="Loading extracted figures" />
  if (extraction.isError) return <ErrorState onRetry={() => void extraction.refetch()} />
  if (!extraction.data) {
    return (
      <EmptyState
        icon={ScanTextIcon}
        title="Not processed yet"
        description="Read the figures from the photo. Without OCR, enter them by hand."
      />
    )
  }
  const data = extraction.data
  const editing = Object.keys(drafts)

  async function save(extra: FieldCorrection[] = []) {
    setError(undefined)
    const corrections: FieldCorrection[] = [...extra]
    for (const key of editing) {
      const field = data.fields.find((item) => item.field_key === key)
      if (!field) continue
      const value = parseValue(field, drafts[key]!.value)
      if (value === 'invalid') return setError(`${field.label} must be a whole number of zero or more.`)
      corrections.push({ field_key: key, value, reason: drafts[key]!.reason.trim() || undefined })
    }
    if (corrections.length === 0) return
    try {
      await correct.mutateAsync(corrections)
      setDrafts({})
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : 'The corrections could not be saved.')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant={data.status === 'completed' ? 'info' : 'warning'}>
          {data.status === 'completed' ? 'OCR completed' : data.status === 'failed' ? 'OCR failed' : 'OCR unavailable'}
        </Badge>
        <span className="text-muted-foreground">
          {data.provider}
          {data.provider_version && ` ${data.provider_version}`} · {formatDateTime(data.created_at)} · threshold{' '}
          {formatConfidence(data.confidence_threshold)}
        </span>
      </div>
      {data.error && (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Manual transcription needed</AlertTitle>
          <AlertDescription>{data.error}</AlertDescription>
        </Alert>
      )}
      {data.attention_fields.length > 0 && (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>{data.attention_fields.length} field(s) need attention</AlertTitle>
          <AlertDescription>
            Compare each highlighted value with the original photo, then correct it or confirm it as read.
          </AlertDescription>
        </Alert>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <caption className="sr-only">Extracted result fields</caption>
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="p-2 font-medium">Field</th>
              <th scope="col" className="p-2 font-medium">Value</th>
              <th scope="col" className="p-2 font-medium">Confidence</th>
              <th scope="col" className="p-2 font-medium">Status</th>
              {canCorrect && <th scope="col" className="p-2 font-medium"><span className="sr-only">Actions</span></th>}
            </tr>
          </thead>
          <tbody className="divide-y">
            {data.fields.map((field) => {
              const draft = drafts[field.field_key]
              return (
                <tr
                  key={field.field_key}
                  className={field.requires_review ? 'bg-warning-subtle/60' : selectedKey === field.field_key ? 'bg-muted' : ''}
                >
                  <th scope="row" className="p-2 text-left align-top font-medium">
                    <button
                      type="button"
                      className="text-left underline-offset-2 hover:underline"
                      onClick={() => onSelectField(field)}
                    >
                      {field.label}
                    </button>
                    {field.required && <span className="sr-only"> (required)</span>}
                    {field.source_text && (
                      <span className="block text-xs font-normal text-muted-foreground">OCR read “{field.source_text}”</span>
                    )}
                  </th>
                  <td className="p-2 align-top">
                    {draft ? (
                      <div className="space-y-1.5">
                        <Input
                          aria-label={`New value for ${field.label}`}
                          inputMode={field.kind === 'integer' ? 'numeric' : 'text'}
                          value={draft.value}
                          onChange={(event) =>
                            setDrafts({ ...drafts, [field.field_key]: { ...draft, value: event.target.value } })
                          }
                        />
                        <Input
                          aria-label={`Reason for changing ${field.label}`}
                          placeholder="Reason (required when changing a value)"
                          value={draft.reason}
                          onChange={(event) =>
                            setDrafts({ ...drafts, [field.field_key]: { ...draft, reason: event.target.value } })
                          }
                        />
                      </div>
                    ) : (
                      <span className="font-mono tabular-nums">{display(field.value)}</span>
                    )}
                    {field.origin === 'human' && field.ocr_value !== field.value && (
                      <span className="block text-xs text-muted-foreground">OCR read {display(field.ocr_value)}</span>
                    )}
                  </td>
                  <td className="p-2 align-top">
                    {field.origin === 'human' ? (
                      <Badge variant="success">Human-checked</Badge>
                    ) : (
                      <Badge variant={confidenceTone(field.confidence, data.confidence_threshold)}>
                        {formatConfidence(field.confidence)}
                      </Badge>
                    )}
                  </td>
                  <td className="p-2 align-top">
                    {field.requires_review ? (
                      <ul className="space-y-0.5 text-xs text-warning">
                        {field.review_reasons.map((reason) => (
                          <li key={reason}>{reviewReasonLabel(reason)}</li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-xs text-muted-foreground">OK</span>
                    )}
                    {field.history.length > 1 && (
                      <button
                        type="button"
                        className="mt-1 flex items-center gap-1 text-xs text-navy"
                        aria-expanded={historyFor === field.field_key}
                        onClick={() => setHistoryFor(historyFor === field.field_key ? null : field.field_key)}
                      >
                        <HistoryIcon className="size-3" aria-hidden /> {field.history.length} versions
                      </button>
                    )}
                    {historyFor === field.field_key && (
                      <ol className="mt-1 space-y-1 text-xs text-muted-foreground">
                        {field.history.map((version) => (
                          <li key={version.version}>
                            v{version.version} · {version.origin === 'ocr' ? 'OCR' : 'person'} · {display(version.value)}
                            {version.reason && ` · “${version.reason}”`} · {formatDateTime(version.created_at)}
                          </li>
                        ))}
                      </ol>
                    )}
                  </td>
                  {canCorrect && (
                    <td className="p-2 text-right align-top whitespace-nowrap">
                      {!draft && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setDrafts({
                              ...drafts,
                              [field.field_key]: { value: field.value === null ? '' : String(field.value), reason: '' },
                            })
                          }
                        >
                          <PencilIcon />
                          Edit
                        </Button>
                      )}
                      {!draft && field.requires_review && field.value !== null && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={correct.isPending}
                          onClick={() => void save([{ field_key: field.field_key, value: field.value, confirm: true }])}
                        >
                          <CheckIcon />
                          Confirm
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
      {editing.length > 0 && (
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDrafts({})}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={correct.isPending}>
            Save {editing.length} correction{editing.length === 1 ? '' : 's'}
          </Button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {data.disclaimer} Corrections are stored as new versions; the original OCR output is never overwritten.
      </p>
      <p className="text-xs text-muted-foreground">{data.template_notice}</p>
    </div>
  )
}
