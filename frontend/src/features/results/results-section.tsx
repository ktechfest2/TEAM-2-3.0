import { Route, Routes } from 'react-router'
import { NotFoundPage } from '@/app/not-found-page'
import { ResultsBaseContext } from '@/features/results/format'
import { PollingUnitRecordsPage } from '@/features/results/polling-unit-records-page'
import { PollingUnitResultPage } from '@/features/results/polling-unit-result-page'
import { ResultsDashboardPage } from '@/features/results/results-dashboard-page'

/** National → state → LGA → ward → polling unit. Mounted publicly and inside the admin console. */
export function ResultsSection({ base = '/results', staff = false }: { base?: string; staff?: boolean }) {
  return (
    <ResultsBaseContext.Provider value={{ base, staff }}>
      <div className={staff ? undefined : 'mx-auto max-w-7xl px-4 py-10 sm:px-6'}>
        <Routes>
          <Route index element={<ResultsDashboardPage level="national" />} />
          <Route path="states/:id" element={<ResultsDashboardPage level="state" />} />
          <Route path="lgas/:id" element={<ResultsDashboardPage level="lga" />} />
          <Route path="wards/:id" element={<ResultsDashboardPage level="ward" />} />
          <Route path="polling-units/:id" element={<PollingUnitResultPage />} />
          <Route path="records" element={<PollingUnitRecordsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </div>
    </ResultsBaseContext.Provider>
  )
}
