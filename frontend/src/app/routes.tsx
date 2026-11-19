import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import type { RouteObject } from 'react-router'
import { adminNavItem } from '@/app/navigation'
import { NotFoundPage } from '@/app/not-found-page'
import { RouteErrorPage } from '@/app/route-error-page'
import { LoadingState } from '@/components/feedback/states'
import { RequireRole } from '@/features/auth/require-role'
import { ADMIN_CONSOLE_ROLES, EVIDENCE_STAFF_ROLES, EVIDENCE_SUBMITTER_ROLES } from '@/features/auth/roles'
import { HomePage } from '@/features/public/home/home-page'
import { VerificationInfoPage } from '@/features/public/verification/verification-info-page'
import { AdminLayout } from '@/layouts/admin-layout'
import { PublicLayout } from '@/layouts/public-layout'

function PageLoading() {
  return <LoadingState />
}

/** Lazily loads a route element so admin and form-heavy code stays out of the public bundle. */
function lazyElement(load: () => Promise<ReactNode>): Pick<RouteObject, 'lazy' | 'HydrateFallback'> {
  return {
    HydrateFallback: PageLoading,
    lazy: async () => ({ element: await load() }),
  }
}

function guarded(path: string, element: ReactNode) {
  return <RequireRole roles={adminNavItem(path).roles}>{element}</RequireRole>
}

const adminModules = () => import('@/features/admin/modules')

/**
 * Code-split public page. Uses React.lazy rather than route `lazy` so the page
 * renders inside the already-mounted layout without a hydration fallback.
 */
function lazyPage(load: () => Promise<ComponentType>) {
  const Page = lazy(async () => ({ default: await load() }))
  return (
    <Suspense fallback={<PageLoading />}>
      <Page />
    </Suspense>
  )
}

const pollingUnitFinder = lazyPage(async () => (await import('@/features/polling-units/polling-unit-finder-page')).PollingUnitFinderPage)
const pollingUnitDetail = lazyPage(async () => (await import('@/features/polling-units/polling-unit-detail-page')).PollingUnitDetailPage)
const updatesList = lazyPage(async () => (await import('@/features/updates/updates-page')).UpdatesPage)
const updateDetail = lazyPage(async () => (await import('@/features/updates/update-detail-page')).UpdateDetailPage)
const resultsSection = lazyPage(async () => (await import('@/features/results/results-section')).ResultsSection)
const submitEvidence = lazyPage(async () => (await import('@/features/evidence/submit-evidence-page')).SubmitEvidencePage)
const myEvidence = lazyPage(async () => (await import('@/features/evidence/my-evidence-page')).MyEvidencePage)
const fieldEvidenceDetail = lazyPage(async () => {
  const { EvidenceDetailPage } = await import('@/features/evidence/evidence-detail-page')
  return () => <EvidenceDetailPage backTo="/evidence" backLabel="My submissions" />
})

/** Field evidence requires a signed-in observer or party agent; the API enforces the same rule. */
function submitterOnly(element: ReactNode) {
  return (
    <RequireRole roles={EVIDENCE_SUBMITTER_ROLES}>
      <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">{element}</div>
    </RequireRole>
  )
}

const reportIncident = lazyPage(
  async () => (await import('@/features/public/incidents/report-incident-page')).ReportIncidentPage,
)
const publicIncidents = lazyPage(
  async () => (await import('@/features/public/incidents/public-incidents-page')).PublicIncidentsPage,
)
const phoneAccess = lazyPage(async () => (await import('@/features/channels/phone-access-page')).PhoneAccessPage)

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <PublicLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'polling-units', element: pollingUnitFinder },
      { path: 'polling-units/:pollingUnitId', element: pollingUnitDetail },
      { path: 'results/*', element: resultsSection },
      { path: 'verification', element: <VerificationInfoPage /> },
      { path: 'updates', element: updatesList },
      { path: 'updates/:updateId', element: updateDetail },
      { path: 'report-incident', element: reportIncident },
      { path: 'incidents', element: publicIncidents },
      { path: 'phone-access', element: phoneAccess },
      { path: 'evidence', element: submitterOnly(myEvidence) },
      { path: 'evidence/submit', element: submitterOnly(submitEvidence) },
      { path: 'evidence/:submissionId', element: submitterOnly(fieldEvidenceDetail) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    path: '/admin/sign-in',
    errorElement: <RouteErrorPage />,
    ...lazyElement(async () => {
      const { SignInPage } = await import('@/features/auth/sign-in-page')
      return <SignInPage />
    }),
  },
  {
    path: '/account/password',
    errorElement: <RouteErrorPage />,
    ...lazyElement(async () => {
      const { ChangePasswordPage } = await import('@/features/auth/change-password-page')
      return <ChangePasswordPage />
    }),
  },
  {
    path: '/admin',
    element: (
      <RequireRole roles={ADMIN_CONSOLE_ROLES}>
        <AdminLayout />
      </RequireRole>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        ...lazyElement(async () => {
          const { OverviewPage } = await import('@/features/admin/overview/overview-page')
          return <OverviewPage />
        }),
      },
      {
        path: 'results/*',
        ...lazyElement(async () => {
          const { ResultsSection } = await import('@/features/results/results-section')
          return guarded('/admin/results', <ResultsSection base="/admin/results" staff />)
        }),
      },
      {
        path: 'evidence',
        ...lazyElement(async () => {
          const { EvidenceSubmissionsPage } = await adminModules()
          return guarded('/admin/evidence', <EvidenceSubmissionsPage />)
        }),
      },
      {
        path: 'evidence/:submissionId',
        ...lazyElement(async () => {
          const { EvidenceDetailPage } = await import('@/features/evidence/evidence-detail-page')
          return (
            <RequireRole roles={EVIDENCE_STAFF_ROLES}>
              <EvidenceDetailPage backTo="/admin/evidence" backLabel="Evidence submissions" />
            </RequireRole>
          )
        }),
      },
      {
        path: 'verification',
        ...lazyElement(async () => {
          const { VerificationReviewPage } = await adminModules()
          return guarded('/admin/verification', <VerificationReviewPage />)
        }),
      },
      {
        path: 'incidents',
        ...lazyElement(async () => {
          const { IncidentManagementPage } = await adminModules()
          return guarded('/admin/incidents', <IncidentManagementPage />)
        }),
      },
      {
        path: 'incidents/:incidentId',
        ...lazyElement(async () => {
          const { IncidentDetailPage } = await adminModules()
          return guarded('/admin/incidents', <IncidentDetailPage />)
        }),
      },
      {
        path: 'polling-units',
        ...lazyElement(async () => {
          const { PollingUnitManagementPage } = await adminModules()
          return guarded('/admin/polling-units', <PollingUnitManagementPage />)
        }),
      },
      {
        path: 'audit-logs',
        ...lazyElement(async () => {
          const { AuditLogsPage } = await adminModules()
          return guarded('/admin/audit-logs', <AuditLogsPage />)
        }),
      },
      {
        path: 'settings',
        ...lazyElement(async () => {
          const { SettingsPage } = await adminModules()
          return guarded('/admin/settings', <SettingsPage />)
        }),
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]
