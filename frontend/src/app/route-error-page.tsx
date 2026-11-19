import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { ErrorState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n/locale-provider'

export function RouteErrorPage() {
  const t = useT()
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : t('An unexpected error occurred while displaying this page.')

  if (import.meta.env.DEV) console.error(error)

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-surface px-4">
      <ErrorState
        title={t('This page could not be displayed')}
        message={message}
        onRetry={() => window.location.reload()}
        className="w-full max-w-lg"
      />
      <Button asChild variant="link">
        <Link to="/">{t('Return to home page')}</Link>
      </Button>
    </div>
  )
}
