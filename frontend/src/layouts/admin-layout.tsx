import { ExternalLinkIcon, KeyRoundIcon, LogOutIcon, MenuIcon, ShieldIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
import { ADMIN_NAV, type AdminNavItem } from '@/app/navigation'
import { useRouteMeta } from '@/app/seo'
import { Logo } from '@/components/brand/logo'
import { LanguageSwitcher } from '@/components/i18n/language-switcher'
import { OfflineBanner } from '@/components/layout/offline-banner'
import { RouteProgress } from '@/components/layout/route-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { useAuth } from '@/features/auth/auth-context'
import { hasAnyRole, ROLE_LABELS, ROLES, type Role } from '@/features/auth/roles'
import { useT } from '@/i18n/locale-provider'
import { cn } from '@/lib/utils'

function SidebarNav({
  roles,
  onNavigate,
  dark = false,
}: {
  roles: readonly Role[]
  onNavigate?: () => void
  dark?: boolean
}) {
  const t = useT()
  const visible = ADMIN_NAV.filter((item) => hasAnyRole(roles, item.roles))
  const groups = visible.reduce<Record<string, AdminNavItem[]>>((acc, item) => {
    ;(acc[item.group] ??= []).push(item)
    return acc
  }, {})

  return (
    <nav aria-label={t('Administration')} className="flex flex-col gap-6 p-3">
      {Object.entries(groups).map(([group, items]) => (
        <div key={group}>
          <p
            className={cn(
              'px-3 pb-2 text-xs font-medium',
              dark ? 'text-white/55' : 'text-muted-foreground',
            )}
          >
            {t(group)}
          </p>
          <ul className="flex flex-col gap-0.5">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      dark
                        ? isActive
                          ? 'bg-white/10 text-white shadow-[inset_3px_0_0_var(--primary)]'
                          : 'text-white/70 hover:bg-white/5 hover:text-white'
                        : isActive
                          ? 'bg-accent text-accent-foreground'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    )
                  }
                >
                  <item.icon className="size-4 shrink-0" aria-hidden />
                  {t(item.label)}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

export function AdminLayout() {
  const t = useT()
  useRouteMeta()
  const { user, isPreview, provider, signOut } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const roles = user?.roles ?? []
  const primaryRole = ROLES.filter((role) => roles.includes(role)).at(-1)

  return (
    <div className="flex min-h-dvh bg-surface">
      <RouteProgress />
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col bg-navy text-white lg:flex">
        <div className="flex h-16 items-center border-b border-white/10 px-5">
          <Link to="/admin" aria-label={t('Admin overview')}>
            <Logo inverted />
          </Link>
        </div>
        <div className="flex-1 overflow-y-auto">
          <SidebarNav roles={roles} dark />
        </div>
        <div className="border-t border-white/10 p-3">
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="w-full justify-start text-white/70 hover:bg-white/5 hover:text-white"
          >
            <Link to="/">
              <ExternalLinkIcon />
              {t('View public site')}
            </Link>
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background px-4 sm:px-6">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t('Open navigation')}>
                <MenuIcon className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left">
              <div className="flex h-16 items-center border-b px-5">
                <SheetTitle asChild>
                  <div>
                    <Logo />
                  </div>
                </SheetTitle>
                <SheetDescription className="sr-only">{t('Administration navigation')}</SheetDescription>
              </div>
              <div className="flex-1 overflow-y-auto">
                <SidebarNav roles={roles} onNavigate={() => setMobileOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>

          <div className="flex items-center gap-2 text-sm font-medium">
            <ShieldIcon className="size-4 text-navy" aria-hidden />
            <span>{t('Administration')}</span>
          </div>

          <div className="ml-auto flex items-center gap-3">
            {primaryRole && (
              <Badge variant="neutral" className="hidden sm:inline-flex">
                {t(ROLE_LABELS[primaryRole])}
              </Badge>
            )}
            <span className="hidden max-w-48 truncate text-sm text-muted-foreground md:inline">{user?.email}</span>
            {!isPreview && provider === 'local' && (
              <Button asChild variant="ghost" size="sm">
                <Link to="/account/password">
                  <KeyRoundIcon />
                  <span className="hidden sm:inline">{t('Password')}</span>
                </Link>
              </Button>
            )}
            {!isPreview && (
              <Button variant="outline" size="sm" onClick={() => void signOut()}>
                <LogOutIcon />
                <span className="hidden sm:inline">{t('Sign out')}</span>
              </Button>
            )}
            <LanguageSwitcher />
          </div>
        </header>

        {isPreview && (
          <div role="status" className="border-b border-info/20 bg-info-subtle px-4 py-2 text-sm sm:px-6">
            <strong className="font-medium">{t('Development preview.')}</strong>{' '}
            <span className="text-muted-foreground">{t('Sign-in is skipped here. The API still requires a session.')}</span>
          </div>
        )}
        <OfflineBanner />

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
