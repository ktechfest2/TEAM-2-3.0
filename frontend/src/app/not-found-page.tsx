import { CompassIcon } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { EmptyState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n/locale-provider'

export function NotFoundPage() {
  const t = useT()
  const { pathname } = useLocation()
  const home = pathname.startsWith('/admin') ? '/admin' : '/'
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <EmptyState
        icon={CompassIcon}
        heading="h1"
        title={t('Page not found')}
        description={t('The page you are looking for does not exist or has moved.')}
        action={
          <Button asChild>
            <Link to={home}>{home === '/admin' ? t('Back to overview') : t('Go to home page')}</Link>
          </Button>
        }
      />
    </div>
  )
}
