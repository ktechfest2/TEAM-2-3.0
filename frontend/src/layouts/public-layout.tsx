import { MenuIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import type { NavItem } from '@/app/navigation'
import { PUBLIC_NAV, REPORT_INCIDENT_NAV } from '@/app/navigation'
import { useRouteMeta } from '@/app/seo'
import { Logo } from '@/components/brand/logo'
import { LanguageSwitcher } from '@/components/i18n/language-switcher'
import { OfflineBanner } from '@/components/layout/offline-banner'
import { RouteProgress } from '@/components/layout/route-progress'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { useT } from '@/i18n/locale-provider'
import { cn } from '@/lib/utils'

const APP_TABS: { item: NavItem; short: string }[] = [
  { item: PUBLIC_NAV[0], short: 'Home' },
  { item: PUBLIC_NAV[2], short: 'Results' },
  { item: PUBLIC_NAV[1], short: 'Find' },
  { item: REPORT_INCIDENT_NAV, short: 'Report' },
]

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cn(
    'px-1 py-2 text-[15px] font-medium transition-colors',
    isActive ? 'text-navy' : 'text-navy hover:opacity-70',
  )
}

export function PublicLayout() {
  const t = useT()
  useRouteMeta()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  const isHome = pathname === '/'
  const footer = [
    {
      title: t('Explore'),
      links: PUBLIC_NAV.slice(1).map((item) => ({ to: item.to, label: t(item.label) })),
    },
    {
      title: t('Participate'),
      links: [
        { to: REPORT_INCIDENT_NAV.to, label: t(REPORT_INCIDENT_NAV.label) },
        { to: '/incidents', label: t('Incident summary') },
        { to: '/phone-access', label: t('USSD and SMS access') },
        { to: '/evidence/submit', label: t('Submit evidence') },
        { to: '/admin', label: t('Staff sign-in') },
      ],
    },
    {
      title: t('About'),
      links: [
        { to: '/verification', label: t('How verification works') },
        { to: '/updates', label: t('Updates') },
      ],
    },
  ]

  return (
    <div className="flex min-h-dvh flex-col overflow-x-hidden bg-background">
      <RouteProgress />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:shadow"
      >
        {t('Skip to content')}
      </a>

      <div className={isHome ? 'overflow-x-hidden bg-hero' : 'bg-background'}>
        <div className="hidden bg-navy text-white lg:block">
          <div className="mx-auto flex max-w-[1240px] items-center justify-center px-4 py-2.5 text-center sm:px-6">
            <Link to="/verification" className="text-[13px] font-medium text-white hover:opacity-80">
              {t('Independent civic verification. Figures are not INEC declarations.')}
            </Link>
          </div>
        </div>

        <header className="sticky top-0 z-40 max-lg:border-b max-lg:border-navy/10 max-lg:bg-background lg:bg-transparent">
          <div className="flex h-14 w-full items-center gap-3 px-4 sm:gap-8 sm:pr-8 sm:pl-5 lg:h-[72px]">
            <Link to="/" aria-label={t('VoteTrace home')} className="shrink-0">
              <Logo />
            </Link>

            <nav aria-label={t('Primary')} className="hidden flex-1 items-center gap-7 lg:flex">
              {PUBLIC_NAV.filter((item) => item.to !== '/').map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
                  {t(item.label)}
                </NavLink>
              ))}
            </nav>

            <div className="ml-auto flex items-center gap-3 sm:gap-5">
              <Link to="/admin" className="hidden text-[15px] font-medium text-navy hover:opacity-70 lg:inline-flex">
                {t('Staff sign-in')}
              </Link>
              <Button asChild className="hidden h-10 px-[18px] sm:inline-flex">
                <Link to={REPORT_INCIDENT_NAV.to}>{t(REPORT_INCIDENT_NAV.label)}</Link>
              </Button>
              <LanguageSwitcher />

              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetContent side="bottom" className="rounded-t-2xl pb-[env(safe-area-inset-bottom)]">
                  <div className="border-b px-4 py-4">
                    <SheetTitle asChild>
                      <div>
                        <Logo showTagline />
                      </div>
                    </SheetTitle>
                    <SheetDescription className="sr-only">{t('Site navigation')}</SheetDescription>
                  </div>
                  <nav aria-label={t('Mobile')} className="flex flex-col gap-1 overflow-y-auto p-3">
                    {[...PUBLIC_NAV, REPORT_INCIDENT_NAV].map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        onClick={() => setMobileOpen(false)}
                        className={({ isActive }) => cn(navLinkClass({ isActive }), 'flex items-center gap-3 px-3')}
                      >
                        <item.icon className="size-4" aria-hidden />
                        {t(item.label)}
                      </NavLink>
                    ))}
                    {footer[1].links
                      .filter((link) => link.to !== REPORT_INCIDENT_NAV.to)
                      .map((link) => (
                        <Link
                          key={link.to}
                          to={link.to}
                          onClick={() => setMobileOpen(false)}
                          className="px-3 py-2 text-[15px] font-medium text-navy"
                        >
                          {link.label}
                        </Link>
                      ))}
                  </nav>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </header>
      </div>

      <OfflineBanner />

      <main id="main" className="flex-1">
        <Outlet />
      </main>

      <nav
        aria-label={t('Sections')}
        className="fixed inset-x-0 bottom-0 z-40 border-t bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        <ul className="grid grid-cols-5">
          {APP_TABS.map(({ item, short }) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex h-16 flex-col items-center justify-center gap-1 px-1 text-[11px] font-medium',
                    isActive ? 'text-primary' : 'text-navy/55',
                  )
                }
              >
                <item.icon className="size-5" aria-hidden />
                {t(short)}
              </NavLink>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              className={cn(
                'flex h-16 w-full flex-col items-center justify-center gap-1 text-[11px] font-medium',
                mobileOpen ? 'text-primary' : 'text-navy/55',
              )}
            >
              <MenuIcon className="size-5" aria-hidden />
              {t('More')}
            </button>
          </li>
        </ul>
      </nav>

      <footer className="border-t bg-white pb-20 text-navy lg:pb-0">
        <div className="mx-auto hidden max-w-[1240px] gap-10 px-4 py-16 sm:px-6 lg:grid lg:grid-cols-4">
          <div>
            <Logo showTagline />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-navy/70">
              {t('Independent civic verification of polling-unit evidence. Not affiliated with INEC.')}
            </p>
          </div>
          {footer.map((group) => (
            <div key={group.title}>
              <h2 className="text-sm font-medium text-navy">{group.title}</h2>
              <ul className="mt-4 space-y-2.5 text-sm">
                {group.links.map((link) => (
                  <li key={link.to + link.label}>
                    <Link to={link.to} className="text-navy/70 hover:text-navy">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="border-t">
          <div className="mx-auto max-w-[1240px] px-4 py-5 text-xs text-navy/50 sm:px-6">
            {t('Official results are declared by the Independent National Electoral Commission (INEC).')}
          </div>
        </div>
      </footer>
    </div>
  )
}
