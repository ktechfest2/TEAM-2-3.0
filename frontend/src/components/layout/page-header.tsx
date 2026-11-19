import type { ReactNode } from 'react'
import { usePageTitle } from '@/app/seo'
import { cn } from '@/lib/utils'

type PageHeaderProps = {
  title: string
  description?: ReactNode
  eyebrow?: string
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, eyebrow, actions, className }: PageHeaderProps) {
  usePageTitle(title)
  return (
    <div className={cn('flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        {eyebrow && <p className="mb-1.5 text-sm text-muted-foreground">{eyebrow}</p>}
        <h1 className="text-2xl font-extrabold tracking-tight text-navy sm:text-[1.75rem]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground sm:text-base">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  )
}
