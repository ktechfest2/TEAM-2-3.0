import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { adminNavItem } from '@/app/navigation'
import { EmptyState } from '@/components/feedback/states'
import { PageHeader } from '@/components/layout/page-header'
import { PlannedModule } from '@/components/layout/planned-module'
import { useT } from '@/i18n/locale-provider'

type AdminModulePageProps = {
  route: string
  description: string
  emptyTitle: string
  emptyDescription: ReactNode
  capabilities: string[]
  note?: string
  emptyIcon?: LucideIcon
}

/** Scaffold for admin modules that are routed and guarded but not yet implemented. */
export function AdminModulePage({
  route,
  description,
  emptyTitle,
  emptyDescription,
  capabilities,
  note,
  emptyIcon,
}: AdminModulePageProps) {
  const t = useT()
  const nav = adminNavItem(route)
  return (
    <div className="space-y-6">
      <PageHeader title={t(nav.label)} description={description} />
      <EmptyState icon={emptyIcon ?? nav.icon} title={emptyTitle} description={emptyDescription} />
      <PlannedModule capabilities={capabilities} note={note} />
    </div>
  )
}
