import {
  ArrowRightIcon,
  BarChart3Icon,
  CameraIcon,
  CheckIcon,
  ClipboardCheckIcon,
  MapPinIcon,
  MegaphoneIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
} from 'lucide-react'
import { Link } from 'react-router'
import { REPORT_INCIDENT_NAV } from '@/app/navigation'
import { LoadingState } from '@/components/feedback/states'
import { Button } from '@/components/ui/button'
import { useUpdates } from '@/features/directory/api'
import { FreshnessNote } from '@/features/directory/data-notice'
import { HeroNigeriaMap } from '@/features/public/home/hero-nigeria-map'
import { AudienceIcon, FeaturePhoto } from '@/features/public/home/home-illustrations'
import { StateArms } from '@/features/public/home/state-arms'
import { UpdateCard } from '@/features/updates/update-card'
import { useT } from '@/i18n/locale-provider'

function useHomeCopy() {
  const t = useT()
  return {
    features: [
      {
        title: t('Capture evidence at the polling unit'),
        body: t(
          'Observers photograph the result sheet, even offline. The original is stored privately.',
        ),
        points: [t('Camera or file upload'), t('Works offline'), t('SHA-256 fingerprint of every sheet')],
        src: '/images/feature-capture.jpg',
        alt: t('An observer photographing a polling-unit result sheet on a smartphone'),
        icon: CameraIcon,
        reversed: false,
      },
      {
        title: t('Independent review, not a black box'),
        body: t(
          'Reviewers check each sheet against the recorded figures. Two approvals are needed to verify.',
        ),
        points: [t('Deterministic arithmetic checks'), t('Two reviewer approvals'), t('Every decision is logged')],
        src: '/images/feature-review.jpg',
        alt: t('Two reviewers comparing a result sheet with records on a laptop'),
        icon: ClipboardCheckIcon,
        reversed: true,
      },
      {
        title: t('Transparent status at every level'),
        body: t(
          'Every polling unit shows its status. Conflicts are listed, and reported and verified totals stay separate.',
        ),
        points: [
          t('Reported and verified kept separate'),
          t('Conflicts excluded from totals'),
          t('Coverage shown, never a winner'),
        ],
        src: '/images/feature-status.jpg',
        alt: t('A laptop showing a Nigeria map dashboard of polling-unit verification status'),
        icon: ShieldCheckIcon,
        reversed: false,
      },
    ],
    audiences: [
      {
        title: t('Find your polling unit'),
        body: t('Search by state, LGA, ward, name or code.'),
        to: '/polling-units',
        icon: MapPinIcon,
      },
      {
        title: t('View results'),
        body: t('Reviewed results by level, with their status.'),
        to: '/results',
        icon: BarChart3Icon,
      },
      {
        title: t('Election updates'),
        body: t('Relocations, schedules and notices, with sources.'),
        to: '/updates',
        icon: MegaphoneIcon,
      },
      {
        title: t('Report an incident'),
        body: t('Record what you witnessed, even offline.'),
        to: REPORT_INCIDENT_NAV.to,
        icon: TriangleAlertIcon,
      },
    ],
  }
}

function LatestUpdates() {
  const t = useT()
  const updates = useUpdates({ pageSize: 3 })
  return (
    <section className="bg-offwhite" aria-labelledby="latest-updates-heading">
      <div className="mx-auto max-w-[1240px] px-4 py-12 sm:px-6 lg:py-24">
        <h2 id="latest-updates-heading" className="text-[28px] leading-tight font-extrabold text-navy sm:text-[45px]">
          {t('Latest election updates')}
        </h2>
        <p className="mt-3 max-w-xl text-[18px] text-navy/80">{t('Relocations, schedules and notices, with sources.')}</p>
        <div className="mt-10">
          {updates.isPending ? (
            <LoadingState variant="skeleton" rows={2} label={t('Loading updates')} />
          ) : updates.isError ? (
            <p className="text-sm text-muted-foreground">
              {t('Updates could not be loaded right now.')}{' '}
              <Link to="/updates" className="font-medium text-navy underline">
                {t('Open the updates page')}
              </Link>
            </p>
          ) : updates.data.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('No election updates have been published yet.')}</p>
          ) : (
            <div className="space-y-3">
              {updates.data.origin === 'cache' && <FreshnessNote result={updates.data} />}
              <ul className="grid gap-6 md:grid-cols-3">
                {updates.data.data.items.map((update) => (
                  <li key={update.id}>
                    <UpdateCard update={update} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <p className="mt-8">
          <Link to="/updates" className="text-[15px] font-medium text-navy hover:underline">
            {t('All updates')}
          </Link>
        </p>
      </div>
    </section>
  )
}

export function HomePage() {
  const t = useT()
  const { features, audiences } = useHomeCopy()
  return (
    <>
      <section className="relative overflow-hidden bg-hero">
        <div className="relative mx-auto grid max-w-[1240px] items-center gap-8 px-4 pt-8 pb-10 sm:px-6 lg:grid-cols-2 lg:gap-8 lg:pt-20 lg:pb-20">
          <div>
            <h1 className="text-[30px] leading-[1.2] font-extrabold text-navy sm:text-[44px]">
              {t('Polling-unit results, backed by verifiable evidence.')}
            </h1>
            <p className="mt-4 max-w-md text-[17px] leading-snug text-navy">
              {t('Check polling-unit results against evidence from the ground.')}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
              <Button asChild size="lg" className="h-12 px-8 text-[16px]">
                <Link to="/polling-units">{t('Find your polling unit')}</Link>
              </Button>
              <Link to="/verification" className="text-[15px] font-medium text-primary underline">
                {t('How verification works')}
              </Link>
            </div>
            <p className="mt-8 text-sm font-medium text-navy/80">{t('36 states and the FCT')}</p>
            <StateArms />
          </div>
          <HeroNigeriaMap />
        </div>
      </section>

      <section className="bg-white" aria-labelledby="how-heading">
        <div className="mx-auto max-w-[1240px] px-4 pt-12 sm:px-6 lg:pt-24">
          <h2 id="how-heading" className="text-[28px] leading-tight font-extrabold text-navy sm:text-[45px]">
            {t('Simple, honest results')}
          </h2>
          <p className="mt-3 max-w-xl text-[18px] text-navy/80">{t('Checking a polling-unit result should not be hard.')}</p>
        </div>
        <div className="mx-auto max-w-[1240px] px-4 sm:px-6">
          {features.map((feature) => (
            <article key={feature.title} className="grid items-center gap-8 py-10 lg:grid-cols-2 lg:gap-20 lg:py-16">
              <div className={feature.reversed ? 'lg:order-2' : undefined}>
                <FeaturePhoto src={feature.src} alt={feature.alt} />
              </div>
              <div className={feature.reversed ? 'lg:order-1' : undefined}>
                <feature.icon className="mb-4 size-8 text-primary" strokeWidth={1.75} aria-hidden />
                <h3 className="text-[28px] leading-snug font-extrabold text-navy sm:text-[36px]">{feature.title}</h3>
                <p className="mt-4 max-w-md text-[16px] leading-relaxed text-navy/80">{feature.body}</p>
                <ul className="mt-6 space-y-3 text-[16px] text-navy">
                  {feature.points.map((point) => (
                    <li key={point} className="flex gap-3">
                      <CheckIcon className="mt-0.5 size-5 shrink-0 text-primary" strokeWidth={2} aria-hidden />
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-tint" aria-labelledby="actions-heading">
        <div className="mx-auto max-w-[1240px] px-4 py-12 sm:px-6 lg:py-24">
          <h2 id="actions-heading" className="text-[28px] leading-tight font-extrabold text-navy sm:text-[45px]">
            {t('Built for people on the ground')}
          </h2>
          <p className="mt-3 max-w-xl text-[18px] text-navy/80">
            {t('Citizens, observers and reviewers each have a clear place to start.')}
          </p>
          <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:mt-14 lg:grid-cols-4 lg:gap-8">
            {audiences.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className="block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  <AudienceIcon icon={item.icon} />
                  <span className="text-[20px] font-extrabold text-navy">{item.title}</span>
                  <span className="mt-2 block text-[15px] leading-relaxed text-navy/80">{item.body}</span>
                  <ArrowRightIcon className="mt-4 block size-5 text-navy" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <LatestUpdates />

      <section className="bg-navy" aria-labelledby="results-close-heading">
        <div className="mx-auto flex max-w-[1240px] flex-col items-start gap-5 px-4 py-10 sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-12">
          <div className="max-w-xl">
            <h2 id="results-close-heading" className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
              {t('Reviewed results')}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-white/70">
              {t('Shown after the result sheet has been checked.')}
            </p>
          </div>
          <Button asChild className="h-11 w-full px-6 sm:w-auto">
            <Link to="/results">
              {t('View results')}
              <ArrowRightIcon aria-hidden />
            </Link>
          </Button>
        </div>
      </section>
    </>
  )
}
