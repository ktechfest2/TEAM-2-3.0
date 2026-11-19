import { ShieldCheckIcon } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { EmptyState, ErrorState, LoadingState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/features/auth/auth-context'
import { EVIDENCE_STAFF_ROLES, hasAnyRole } from '@/features/auth/roles'
import { formatDateTime } from '@/features/directory/data-notice'
import { useLiveAnalytics, usePollingUnitResult } from '@/features/results/api'
import {
  CachedDataNotice,
  PartyResultsPanel,
  UnitStatusBadge,
} from '@/features/results/dashboard-components'
import { UNIT_STATUS_META, useResultsBase, useSelectedElection } from '@/features/results/format'
import { Breadcrumbs, ElectionSelect } from '@/features/results/results-dashboard-page'
import type { PollingUnitResultResponse, SourceRecord } from '@/features/results/types'

function yesNo(value: boolean | null) {
  if (value === null) return '-'
  return value ? 'Yes' : 'No'
}

function SourceRecords({ records, staff }: { records: SourceRecord[]; staff: boolean }) {
  if (records.length === 0) {
    return <p className="text-sm text-muted-foreground">No evidence has been submitted for this polling unit.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th scope="col" className="py-2 pr-3 font-medium">
              Record
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Received
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Workflow status
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Passed validation
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Matches reported figures
            </th>
            <th scope="col" className="py-2 font-medium">
              Counted
            </th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.submission_id} className="border-b last:border-0">
              <th scope="row" className="py-2 pr-3 text-left font-mono text-xs font-normal">
                {staff ? (
                  <Link to={`/admin/evidence/${record.submission_id}`} className="text-navy hover:underline">
                    {record.submission_id.slice(0, 8)}
                  </Link>
                ) : (
                  record.submission_id.slice(0, 8)
                )}
                {record.result_fingerprint && (
                  <span className="block text-muted-foreground" title="Fingerprint of the transcribed figures">
                    figures #{record.result_fingerprint.slice(0, 10)}
                  </span>
                )}
              </th>
              <td className="py-2 pr-3 text-xs">{formatDateTime(record.received_at)}</td>
              <td className="py-2 pr-3 text-xs">{record.workflow_status.replaceAll('_', ' ').toLowerCase()}</td>
              <td className="py-2 pr-3">{yesNo(record.validation_passed)}</td>
              <td className="py-2 pr-3">{yesNo(record.agrees_with_reported)}</td>
              <td className="py-2">
                {record.contributes ? <Badge variant="success">Counted</Badge> : <Badge variant="neutral">Not counted</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function VerificationReportCard({ data }: { data: PollingUnitResultResponse }) {
  const report = data.verification
  const rows: [string, string][] = [
    ['Submissions received', String(data.unit.submission_count)],
    ['Accepted by validation', String(data.unit.accepted_count)],
    ['Independent sources behind the counted figures', String(data.unit.independent_count)],
    ['Distinct sets of figures', String(data.unit.distinct_results)],
    ['Reviewer approvals on the verified figures', `${report.approvals_on_verified_result} of ${report.required_approvals} required`],
    ['Verified at', formatDateTime(report.verified_at)],
    ['Checks passed / failed / warnings', `${report.checks_passed} / ${report.checks_failed} / ${report.warnings}`],
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <ShieldCheckIcon className="size-4" aria-hidden /> Public verification report
          <UnitStatusBadge status={report.status} />
        </CardTitle>
        <CardDescription>{UNIT_STATUS_META[report.status].description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {rows.map(([term, value]) => (
            <div key={term}>
              <dt className="text-xs text-muted-foreground">{term}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted-foreground">{report.disclaimer}</p>
      </CardContent>
    </Card>
  )
}

export function PollingUnitResultPage() {
  const { id } = useParams()
  const { staff: staffBase } = useResultsBase()
  const { user } = useAuth()
  const staff = staffBase || hasAnyRole(user?.roles ?? [], EVIDENCE_STAFF_ROLES)
  const elections = useSelectedElection()
  const electionId = elections.selected?.id
  const query = usePollingUnitResult(id, electionId)
  useLiveAnalytics(electionId)

  if (elections.query.isPending) return <LoadingState label="Loading elections…" />
  if (!electionId) return <EmptyState title="No elections available" />
  if (query.isPending) return <LoadingState variant="skeleton" rows={5} label="Loading polling unit…" />
  if (query.isError)
    return (
      <ErrorState
        title="Polling unit result could not be loaded"
        message="The polling unit may not be registered for this election, or the service is unreachable."
        onRetry={() => void query.refetch()}
      />
    )

  const data = query.data.data
  return (
    <div className="space-y-6">
      <Breadcrumbs crumbs={data.breadcrumbs} electionId={electionId} />
      <PageHeader
        eyebrow={`Polling unit · ${data.election.name}`}
        title={data.unit.name}
        description={`${data.unit.code} · ${data.unit.ward.name}, ${data.unit.lga.name}, ${data.unit.state.name}`}
        actions={<ElectionSelect items={elections.items} selected={elections.selected} onSelect={elections.select} />}
      />
      <CachedDataNotice result={query.data} />
      {data.unit.registry_incomplete && (
        <Alert variant="warning">
          <AlertTitle>Incomplete location record</AlertTitle>
          <AlertDescription>
            The register does not hold a confirmed address or position for this polling unit. That does not affect how its
            result is counted.
          </AlertDescription>
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <VerificationReportCard data={data} />
        <PartyResultsPanel data={data} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Source records</CardTitle>
          <CardDescription>
            Every submission considered for this polling unit. Submitter identities, photos and storage details are not
            published.
            {staff && ' As staff, you can open each record in the evidence review workspace.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SourceRecords records={data.source_records} staff={staff} />
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        Last aggregation change {formatDateTime(data.unit.updated_at)} · revision {data.unit.revision ?? '-'} · generated{' '}
        {formatDateTime(data.generated_at)}
      </p>
    </div>
  )
}
