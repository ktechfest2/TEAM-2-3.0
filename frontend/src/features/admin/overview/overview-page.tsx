import { Link } from 'react-router'
import { ADMIN_NAV } from '@/app/navigation'
import { useAuth } from '@/features/auth/auth-context'
import { hasAnyRole } from '@/features/auth/roles'
import { useEvidenceList } from '@/features/evidence/api'
import { useIncidentStats } from '@/features/incidents/api'
import { useArea } from '@/features/results/api'
import { formatCount, useSelectedElection } from '@/features/results/format'
import { useHealthQuery } from '@/features/system/api'
import { useT } from '@/i18n/locale-provider'

function Figure({ label, value, to }: { label: string; value: string; to: string }) {
  return (
    <Link to={to} className="block px-4 py-4 hover:bg-muted">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-navy">{value}</p>
    </Link>
  )
}

export function OverviewPage() {
  const t = useT()
  const { user } = useAuth()
  const roles = user?.roles ?? []
  const elections = useSelectedElection()
  const electionId = elections.selected?.id
  const area = useArea('national', undefined, electionId)
  const review = useEvidenceList({ queue: 'review' })
  const incidents = useIncidentStats({})
  const health = useHealthQuery()
  const coverage = area.data?.data.summary.coverage
  const modules = ADMIN_NAV.filter((item) => item.to !== '/admin' && hasAnyRole(roles, item.roles))
  const dash = '-'

  return (
    <div className="space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-navy">{t('Overview')}</h1>
          {elections.selected && <p className="mt-1 text-sm text-muted-foreground">{elections.selected.name}</p>}
        </div>
      </header>

      <dl className="grid grid-cols-2 border-y sm:grid-cols-4">
        <Figure
          label={t('Reporting')}
          value={coverage ? formatCount(coverage.reporting_polling_units) : dash}
          to="/admin/results"
        />
        <Figure
          label={t('Verified')}
          value={coverage ? formatCount(coverage.verified_polling_units) : dash}
          to="/admin/results"
        />
        <Figure
          label={t('In review')}
          value={review.data ? formatCount(review.data.total) : dash}
          to="/admin/verification"
        />
        <Figure
          label={t('Incidents awaiting review')}
          value={incidents.data ? formatCount(incidents.data.awaiting_review) : dash}
          to="/admin/incidents"
        />
      </dl>

      <nav aria-label={t('Your modules')}>
        <ul className="divide-y border-y">
          {modules.map((item) => (
            <li key={item.to}>
              <Link to={item.to} className="flex items-center justify-between py-3 text-sm hover:text-navy">
                <span className="font-medium">{t(item.label)}</span>
                <item.icon className="size-4 text-muted-foreground" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className="text-xs text-muted-foreground">
        {health.data
          ? `${health.data.service} ${health.data.version}. ${
              health.data.database === 'ok' ? t('Postgres connected') : t('Local development database')
            }.`
          : health.isError
            ? t('API unreachable')
            : t('Contacting API…')}
      </p>
    </div>
  )
}
