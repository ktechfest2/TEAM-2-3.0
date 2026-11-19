import { useEffect, useState } from 'react'
import { NIGERIA_STATES } from '@/components/brand/nigeria-states'
import { useT } from '@/i18n/locale-provider'
import { cn } from '@/lib/utils'

const IDLE = '#c7efd4'
const ACTIVE = '#3bb75e'
const VISITED = '#6fd48c'
const STROKE = '#f1fef4'
const STEP_MS = 520

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(media.matches)
    onChange()
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return reduced
}

export function HeroNigeriaMap({ className }: { className?: string }) {
  const t = useT()
  const reduced = usePrefersReducedMotion()
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (reduced) return
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % NIGERIA_STATES.length)
    }, STEP_MS)
    return () => window.clearInterval(timer)
  }, [reduced])

  const active = NIGERIA_STATES[index] ?? NIGERIA_STATES[0]!

  return (
    <figure className={cn('mx-auto w-full max-w-[520px] lg:max-w-none', className)}>
      <svg
        viewBox="0 0 420 343"
        role="img"
        aria-label={t('Map of Nigeria highlighting {name}. All 36 states and the Federal Capital Territory.', {
          name: active.name,
        })}
        className="h-auto w-full"
      >
        {NIGERIA_STATES.map((state, i) => {
          const isActive = !reduced && i === index
          const isVisited = i < index
          return (
            <path
              key={state.iso}
              d={state.d}
              fill={reduced || isActive ? ACTIVE : isVisited ? VISITED : IDLE}
              stroke={STROKE}
              strokeWidth="0.7"
              strokeLinejoin="round"
              style={{ transition: 'fill 280ms ease' }}
            >
              <title>{state.name}</title>
            </path>
          )
        })}
      </svg>
      <figcaption className="mt-4 text-center">
        <span className="block text-[13px] font-medium text-navy/60">
          {reduced ? t('36 states and the FCT') : t('Showing')}
        </span>
        <span aria-live="polite" className="mt-1 block text-[20px] font-extrabold text-navy">
          {reduced ? t('Nigeria') : active.name}
        </span>
      </figcaption>
    </figure>
  )
}
