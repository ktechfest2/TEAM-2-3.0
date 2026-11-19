import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/features/directory/data-notice'
import { UnitStatusBadge } from '@/features/results/dashboard-components'
import { resultsPath, useResultsBase } from '@/features/results/format'
import type { PollingUnitRow } from '@/features/results/types'

export function PollingUnitTable({ items, electionId }: { items: PollingUnitRow[]; electionId: string }) {
  const { base } = useResultsBase()
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th scope="col" className="py-2 pr-3 font-medium">
              Polling unit
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Location
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Status
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Submissions
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium" title="Independent sources behind the counted figures">
              Independent sources
            </th>
            <th scope="col" className="py-2 font-medium">
              Last change
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((unit) => (
            <tr key={unit.id} className="border-b align-top last:border-0">
              <th scope="row" className="py-2 pr-3 text-left font-medium">
                <Link
                  to={resultsPath(base, 'polling_unit', unit.id, electionId)}
                  className="text-navy hover:underline"
                >
                  {unit.name}
                </Link>
                <span className="block text-xs font-normal text-muted-foreground">{unit.code}</span>
              </th>
              <td className="py-2 pr-3 text-xs text-muted-foreground">
                {unit.ward.name}, {unit.lga.name}, {unit.state.name}
              </td>
              <td className="space-x-1 py-2 pr-3">
                <UnitStatusBadge status={unit.status} />
                {unit.has_flagged && unit.status !== 'conflict' && <Badge variant="warning">Flagged</Badge>}
                {unit.has_anomaly && <Badge variant="warning">AI alert</Badge>}
                {unit.registry_incomplete && <Badge variant="neutral">Location record incomplete</Badge>}
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{unit.submission_count}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{unit.independent_count}</td>
              <td className="py-2 text-xs text-muted-foreground">{formatDateTime(unit.updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
