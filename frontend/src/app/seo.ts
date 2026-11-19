import { useEffect, useLayoutEffect } from 'react'
import { useLocation } from 'react-router'

export const SITE_NAME = 'VoteTrace'

const DEFAULT_DESCRIPTION =
  'Check Nigerian polling-unit results against photographed result sheets, reviewed by independent observers.'

type RouteMeta = { title: string; description: string; index: boolean }

/** First path segment to page metadata. Pages refine the title with their own heading. */
const ROUTE_META: Record<string, RouteMeta> = {
  '': { title: `${SITE_NAME} | Every Vote, Every Voice`, description: DEFAULT_DESCRIPTION, index: true },
  'polling-units': {
    title: 'Find your polling unit',
    description: 'Search Nigerian polling units by state, LGA, ward, name or code, and see their location and status.',
    index: true,
  },
  results: {
    title: 'Results',
    description: 'Polling-unit results by state and LGA, with reported and verified figures kept separate.',
    index: true,
  },
  verification: {
    title: 'How verification works',
    description: 'How VoteTrace captures result sheets, checks the figures and verifies them with two independent reviewers.',
    index: true,
  },
  updates: {
    title: 'Election updates',
    description: 'Polling-unit relocations, schedule changes and notices, each with its source and verification status.',
    index: true,
  },
  'report-incident': {
    title: 'Report an incident',
    description: 'Report an election incident you witnessed. Works offline and syncs when you reconnect.',
    index: true,
  },
  incidents: {
    title: 'Incident summary',
    description: 'Counts of reported election incidents by review stage, and summaries of verified incidents.',
    index: true,
  },
  'phone-access': {
    title: 'USSD and SMS access',
    description: 'Check polling-unit information and results from any phone using USSD or SMS.',
    index: true,
  },
  evidence: { title: 'My submissions', description: DEFAULT_DESCRIPTION, index: false },
  admin: { title: 'Administration', description: DEFAULT_DESCRIPTION, index: false },
  account: { title: 'Account', description: DEFAULT_DESCRIPTION, index: false },
}

const SHARE_IMAGE_PATH = '/images/feature-status.jpg'

export function withSite(title: string) {
  return title.startsWith(SITE_NAME) ? title : `${title} | ${SITE_NAME}`
}

export function metaForSegment(segment: string): RouteMeta {
  return ROUTE_META[segment] ?? { title: 'Page not found', description: DEFAULT_DESCRIPTION, index: false }
}

function shareImageUrl() {
  return `${window.location.origin}${SHARE_IMAGE_PATH}`
}

function upsertMeta(attr: 'name' | 'property', key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.content = content
}

function upsertCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.rel = 'canonical'
    document.head.appendChild(el)
  }
  el.href = href
}

function applyTitle(title: string) {
  const full = withSite(title)
  document.title = full
  upsertMeta('property', 'og:title', full)
  upsertMeta('name', 'twitter:title', full)
}

/**
 * Sets the route's default title, description, canonical URL and robots policy.
 * Runs as a layout effect so a page's own `usePageTitle` (a passive effect) wins.
 */
export function useRouteMeta() {
  const { pathname } = useLocation()
  useLayoutEffect(() => {
    const segment = pathname.split('/')[1] ?? ''
    const known = metaForSegment(segment)
    applyTitle(known.title)
    upsertMeta('name', 'description', known.description)
    upsertMeta('property', 'og:description', known.description)
    upsertMeta('name', 'twitter:description', known.description)
    const image = shareImageUrl()
    upsertMeta('property', 'og:image', image)
    upsertMeta('name', 'twitter:image', image)
    upsertMeta('name', 'twitter:card', 'summary_large_image')
    upsertMeta('name', 'robots', known.index ? 'index, follow' : 'noindex, nofollow')
    const url = `${window.location.origin}${pathname === '/' ? '/' : pathname.replace(/\/+$/, '')}`
    upsertCanonical(url)
    upsertMeta('property', 'og:url', url)
  }, [pathname])
}

/** Uses the page heading as the document title. */
export function usePageTitle(title: string | undefined) {
  useEffect(() => {
    if (title) applyTitle(title)
  }, [title])
}
