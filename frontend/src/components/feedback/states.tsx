import { AlertTriangleIcon, InboxIcon, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { useT } from '@/i18n/locale-provider'
import { cn } from '@/lib/utils'

type LoadingStateProps = {
  label?: string
  className?: string
  variant?: 'spinner' | 'skeleton'
  rows?: number
}

export function LoadingState({ label, className, variant = 'spinner', rows = 3 }: LoadingStateProps) {
  const t = useT()
  const text = label ?? t('Loading…')
  if (variant === 'skeleton') {
    return (
      <div className={cn('space-y-3', className)} aria-busy="true" aria-label={text}>
        {Array.from({ length: rows }, (_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    )
  }
  return (
    <div
      className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground', className)}
      aria-busy="true"
    >
      <Spinner />
      <span>{text}</span>
    </div>
  )
}

type ErrorStateProps = {
  title?: string
  message?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({ title, message, onRetry, className }: ErrorStateProps) {
  const t = useT()
  const heading = title ?? t('Something went wrong')
  const body = message ?? t('We could not load this content. Please try again.')
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive-subtle px-6 py-10 text-center',
        className,
      )}
    >
      <AlertTriangleIcon className="mb-3 size-6 text-destructive" aria-hidden />
      <h2 className="text-base font-semibold">{heading}</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{body}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          {t('Try again')}
        </Button>
      )}
    </div>
  )
}

type EmptyStateProps = {
  icon?: LucideIcon
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
  heading?: 'h1' | 'h2'
}

export function EmptyState({ icon: Icon = InboxIcon, title, description, action, className, heading = 'h2' }: EmptyStateProps) {
  const Title = heading
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-dashed bg-surface px-6 py-12 text-center',
        className,
      )}
    >
      <div className="mb-3 flex size-11 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon className="size-5" aria-hidden />
      </div>
      <Title className="text-base font-semibold">{title}</Title>
      {description && <div className="mt-1 max-w-md text-sm text-muted-foreground">{description}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
