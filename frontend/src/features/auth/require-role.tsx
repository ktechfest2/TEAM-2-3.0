import { ShieldAlertIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { EmptyState, LoadingState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/auth-context'
import { CHANGE_PASSWORD_PATH, SIGN_IN_PATH } from '@/features/auth/destination'
import { hasAnyRole, type Role } from '@/features/auth/roles'
import { useT } from '@/i18n/locale-provider'

type RequireRoleProps = {
  roles: readonly Role[]
  children: ReactNode
}

/**
 * Route guard. Redirects anonymous users to sign-in and shows an access
 * notice for authenticated users lacking the role. This is a UX layer only;
 * the API independently authorises every request.
 */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const t = useT()
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <LoadingState label={t('Checking your session…')} className="min-h-[50vh]" />

  if (!user) {
    return <Navigate to={SIGN_IN_PATH} replace state={{ from: location.pathname }} />
  }

  if (user.mustChangePassword) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace state={{ from: location.pathname }} />
  }

  if (!hasAnyRole(user.roles, roles)) {
    return (
      <div className="p-6">
        <EmptyState
          icon={ShieldAlertIcon}
          title={t('You do not have access to this area')}
          description={t('Ask a system administrator if you need access.')}
          action={
            <Button asChild variant="outline">
              <Link to="/">{t('Return to public site')}</Link>
            </Button>
          }
        />
      </div>
    )
  }

  return <>{children}</>
}
