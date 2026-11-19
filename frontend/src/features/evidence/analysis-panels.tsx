import {
  BotIcon,
  CheckCircle2Icon,
  CircleDashedIcon,
  CopyIcon,
  GitCompareArrowsIcon,
  InfoIcon,
  TriangleAlertIcon,
  XCircleIcon,
} from 'lucide-react'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/features/directory/data-notice'
import { useAnomalies, useComparisons, useValidation } from '@/features/evidence/api'
import { AiAlertBadge } from '@/features/evidence/status'
import type { ValidationCheck } from '@/features/evidence/types'

function shortId(id: string) {
  return id.slice(0, 8)
}

function fieldLabel(key: string) {
  return key.startsWith('party:') ? `Party ${key.slice(6)}` : key.replaceAll('_', ' ')
}

const OUTCOME = {
  passed: { icon: CheckCircle2Icon, className: 'text-success', label: 'Passed' },
  failed: { icon: XCircleIcon, className: 'text-destructive', label: 'Failed' },
  not_evaluated: { icon: CircleDashedIcon, className: 'text-muted-foreground', label: 'Not evaluated' },
} as const

function CheckRow({ check }: { check: ValidationCheck }) {
  const outcome = OUTCOME[check.outcome]
  const Icon = outcome.icon
  const isWarning = check.outcome === 'failed' && check.severity === 'warning'
  return (
    <li className="flex gap-3 p-3">
      <Icon className={`mt-0.5 size-4 shrink-0 ${isWarning ? 'text-warning' : outcome.className}`} aria-hidden />
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-medium">
          {check.description}{' '}
          <span className="sr-only">
            {outcome.label}
            {isWarning ? ' (warning)' : ''}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">{check.detail}</p>
      </div>
      {check.severity === 'warning' && (
        <Badge variant="neutral" className="ml-auto self-start">
          warning
        </Badge>
      )}
    </li>
  )
}

export function ValidationPanel({ submissionId }: { submissionId: string }) {
  const validation = useValidation(submissionId)
  if (validation.isPending) return <LoadingState label="Loading validation report" />
  if (validation.isError) return <ErrorState onRetry={() => void validation.refetch()} />
  if (!validation.data) {
    return (
      <EmptyState
        title="Not validated yet"
        description="Run the checks once the figures are reviewed."
      />
    )
  }
  const { report, passed, is_current, result_hash, created_at } = validation.data
  return (
    <div className="space-y-4">
      <Alert variant={passed ? 'success' : 'destructive'}>
        {passed ? <CheckCircle2Icon /> : <XCircleIcon />}
        <AlertTitle>
          {passed
            ? 'The figures are arithmetically consistent'
            : `${report.summary.errors} check${report.summary.errors === 1 ? '' : 's'} failed`}
        </AlertTitle>
        <AlertDescription>{report.disclaimer}</AlertDescription>
      </Alert>
      {!is_current && (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>Out of date</AlertTitle>
          <AlertDescription>Values changed after this report. Validate again before review.</AlertDescription>
        </Alert>
      )}
      <ul className="divide-y rounded-lg border">
        {report.checks.map((check) => (
          <CheckRow key={check.rule_id} check={check} />
        ))}
      </ul>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Missing fields</dt>
          <dd>{report.missing_fields.length ? report.missing_fields.map(fieldLabel).join(', ') : 'None'}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Fields needing attention</dt>
          <dd>{report.attention_fields.length ? report.attention_fields.map(fieldLabel).join(', ') : 'None'}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs text-muted-foreground">Result fingerprint (SHA-256 of the canonical figures)</dt>
          <dd className="font-mono text-xs break-all">{result_hash}</dd>
        </div>
      </dl>
      <p className="text-xs text-muted-foreground">Validated {formatDateTime(created_at)}</p>
    </div>
  )
}

export function ComparisonPanel({ submissionId }: { submissionId: string }) {
  const comparisons = useComparisons(submissionId, true)
  if (comparisons.isPending) return <LoadingState label="Loading comparison" />
  if (comparisons.isError) return <ErrorState onRetry={() => void comparisons.refetch()} />
  const latest = comparisons.data[0]
  if (!latest) {
    return <EmptyState icon={GitCompareArrowsIcon} title="No comparison yet" description="Comparison runs during validation." />
  }
  const { report } = latest
  const columns = report.submission_ids
  return (
    <div className="space-y-4">
      <Alert variant={latest.has_conflicts ? 'warning' : latest.has_duplicates ? 'warning' : 'info'}>
        {latest.has_conflicts ? <TriangleAlertIcon /> : <InfoIcon />}
        <AlertTitle>
          {report.submission_count} submission{report.submission_count === 1 ? '' : 's'} for this polling unit
        </AlertTitle>
        <AlertDescription>{report.recommendation.text}</AlertDescription>
      </Alert>
      {report.submission_count > 1 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">Field-by-field comparison</caption>
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="p-2 font-medium">Field</th>
                {columns.map((id) => (
                  <th key={id} scope="col" className="p-2 font-mono font-medium">
                    {id === submissionId ? 'This submission' : shortId(id)}
                  </th>
                ))}
                <th scope="col" className="p-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {report.fields.map((field) => (
                <tr key={field.field_key} className={field.status === 'conflict' ? 'bg-warning-subtle/60' : ''}>
                  <th scope="row" className="p-2 text-left font-medium">{fieldLabel(field.field_key)}</th>
                  {columns.map((id) => {
                    const differs = field.differing_submissions?.includes(id)
                    return (
                      <td key={id} className={`p-2 font-mono tabular-nums ${differs ? 'font-semibold text-warning' : ''}`}>
                        {field.values[id] ?? 'Not recorded'}
                        {differs && <span className="sr-only"> (differs from the most common value)</span>}
                      </td>
                    )
                  })}
                  <td className="p-2">
                    <Badge variant={field.status === 'match' ? 'success' : field.status === 'conflict' ? 'warning' : 'neutral'}>
                      {field.status === 'match' ? 'Match' : field.status === 'conflict' ? 'Conflict' : 'Incomplete'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report.duplicates.length > 0 && (
        <section aria-labelledby="dup-heading" className="space-y-2">
          <h3 id="dup-heading" className="flex items-center gap-2 text-sm font-semibold">
            <CopyIcon className="size-4" aria-hidden /> Independence and duplicate indicators
          </h3>
          <ul className="space-y-1 text-sm">
            {report.duplicates.map((item) => (
              <li key={`${item.type}-${item.submission_ids.join('-')}`}>
                <Badge variant="warning" className="mr-2">
                  {item.type.replaceAll('_', ' ')}
                </Badge>
                {item.submission_ids.map(shortId).join(' ↔ ')}: {item.detail}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-xs text-muted-foreground">
        Compared {formatDateTime(report.compared_at)}. A difference between submissions is not evidence of wrongdoing by
        anyone; it means a person needs to look at the original images.
      </p>
    </div>
  )
}

export function AnomalyPanel({ submissionId }: { submissionId: string }) {
  const anomalies = useAnomalies(submissionId, true)
  if (anomalies.isPending) return <LoadingState label="Loading AI analysis" />
  if (anomalies.isError) return <ErrorState onRetry={() => void anomalies.refetch()} />
  const { alerts, statistical_analysis: statistical, disclaimer } = anomalies.data
  const current = alerts.filter((alert) => alert.is_current)
  const earlier = alerts.length - current.length
  return (
    <div className="space-y-4">
      <Alert variant="info">
        <BotIcon />
        <AlertTitle>Anomaly check</AlertTitle>
        <AlertDescription>{disclaimer}</AlertDescription>
      </Alert>
      {current.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No anomalies were flagged in the latest analysis. This does not mean the result is correct; human review is
          still required.
        </p>
      ) : (
        <ul className="space-y-3">
          {current.map((alert) => (
            <li key={alert.id} className="space-y-2 rounded-lg border border-warning/30 bg-warning-subtle/40 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <AiAlertBadge severity={alert.severity} />
                <Badge variant="outline">{alert.category.replaceAll('_', ' ')}</Badge>
                {alert.is_demo && <Badge variant="warning">Test model</Badge>}
              </div>
              <p className="font-semibold">{alert.headline}</p>
              <p className="text-sm">{alert.summary}</p>
              {alert.explanation.why && <p className="text-sm text-muted-foreground">Why: {alert.explanation.why}</p>}
              {alert.fields.length > 0 && (
                <p className="text-sm">
                  <span className="text-muted-foreground">Fields: </span>
                  {alert.fields.map(fieldLabel).join(', ')}
                </p>
              )}
              <p className="text-sm font-medium">Recommendation: {alert.recommendation}</p>
              <p className="text-xs text-muted-foreground">
                {alert.model_name} · version {alert.model_version}
              </p>
            </li>
          ))}
        </ul>
      )}
      {earlier > 0 && (
        <p className="text-xs text-muted-foreground">{earlier} alert(s) from earlier analyses are kept in the history.</p>
      )}
      {statistical && (
        <section aria-labelledby="stat-heading" className="space-y-1 rounded-lg border p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id="stat-heading" className="font-semibold">
              Statistical analysis
            </h3>
            {statistical.is_demo && <Badge variant="warning">DEMO / SYNTHETIC</Badge>}
            {statistical.is_outlier && <Badge variant="outline">Statistical outlier</Badge>}
          </div>
          {statistical.status === 'insufficient_data' ? (
            <p className="text-muted-foreground">{statistical.detail}</p>
          ) : (
            <>
              <p className="text-muted-foreground">
                Compared with {statistical.reference_records} human-reviewed records using{' '}
                {statistical.variables.map(fieldLabel).join(', ')}. Anomaly score {statistical.anomaly_score} (lower is
                more unusual)
                {statistical.empirical_p_value &&
                  `; p = ${statistical.empirical_p_value}, flagged at p ≤ ${statistical.alpha ?? 0.05}`}
                .
              </p>
              <p className="text-muted-foreground">
                This compares figures with other reviewed records only. Arithmetic checks and differences between
                submissions are reported separately, and an outlier is not evidence of wrongdoing.
              </p>
              {statistical.contributing_fields && statistical.contributing_fields.length > 0 && (
                <table className="w-full text-left text-xs">
                  <caption className="sr-only">How each ratio compares with the reviewed records</caption>
                  <thead className="text-muted-foreground">
                    <tr>
                      <th scope="col" className="py-1 font-medium">
                        Ratio
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        This record
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        Typical
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        Robust z
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {statistical.contributing_fields.map((c) => (
                      <tr key={c.variable} className={c.unusual ? 'font-semibold' : undefined}>
                        <td className="py-1">{c.description}</td>
                        <td className="py-1">{c.value}</td>
                        <td className="py-1">{c.reference_median}</td>
                        <td className="py-1">
                          {c.robust_z}
                          {c.unusual && ' (unusual)'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          <p className="text-xs text-muted-foreground">
            {statistical.model_name} · {statistical.model_version}
          </p>
        </section>
      )}
    </div>
  )
}
