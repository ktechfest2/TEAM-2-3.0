import { useId } from 'react'
import { FINGERPRINT_RIDGES, NIGERIA_LOGO_PATH, NIGERIA_MAP_PATH } from '@/components/brand/nigeria-outline'
import { useT } from '@/i18n/locale-provider'
import { cn } from '@/lib/utils'

type LogoProps = {
  className?: string
  showTagline?: boolean
  inverted?: boolean
}

/** Paystack primary green for the map, navy ridges, white check inside the print. */
const MAP = '#3bb75e'
const RIDGE = '#011b33'
const CHECK = '#ffffff'

function FingerprintWithCheck({ strokeWidth }: { strokeWidth: number | string }) {
  return (
    <g>
      <g fill="none" stroke={RIDGE} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
        {FINGERPRINT_RIDGES.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <path
        d="M10.2 13.25 11.55 14.55 13.95 11.7"
        fill="none"
        stroke={CHECK}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  )
}

/** Header mark: green Nigeria, fingerprint inside, check inside the fingerprint. */
export function LogoMark({ className }: { className?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg viewBox="0 0 64 53" aria-hidden className={cn('h-8 w-auto shrink-0', className)}>
      <defs>
        <clipPath id={`${id}-clip`}>
          <path d={NIGERIA_LOGO_PATH} />
        </clipPath>
      </defs>
      <path d={NIGERIA_LOGO_PATH} fill={MAP} />
      <g clipPath={`url(#${id}-clip)`}>
        <g transform="translate(16.2 10.4) scale(1.22)">
          <FingerprintWithCheck strokeWidth="1.7" />
        </g>
      </g>
    </svg>
  )
}

/** Hero mark. Same nesting: check inside fingerprint inside Nigeria. */
export function NigeriaMark({ className }: { className?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg
      viewBox="0 0 420 343"
      role="img"
      aria-label="Map of Nigeria with a fingerprint and a verification mark inside it"
      className={cn('h-auto w-full', className)}
    >
      <defs>
        <clipPath id={`${id}-clip`}>
          <path d={NIGERIA_MAP_PATH} />
        </clipPath>
      </defs>
      <path d={NIGERIA_MAP_PATH} fill={MAP} />
      <g clipPath={`url(#${id}-clip)`}>
        <g transform="translate(145 88) scale(5.5)">
          <FingerprintWithCheck strokeWidth="1.5" />
        </g>
      </g>
    </svg>
  )
}

/** Paystack-style dotted map wash used behind the hero. */
export function DottedNigeria({ className }: { className?: string }) {
  const id = useId().replace(/:/g, '')
  const dots: Array<{ x: number; y: number }> = []
  for (let y = 14; y < 330; y += 14) {
    const offset = Math.floor(y / 14) % 2 === 0 ? 0 : 7
    for (let x = 8 + offset; x < 412; x += 14) {
      dots.push({ x, y })
    }
  }
  return (
    <svg viewBox="0 0 420 343" aria-hidden className={cn('h-auto w-full', className)}>
      <defs>
        <clipPath id={`${id}-dots`}>
          <path d={NIGERIA_MAP_PATH} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id}-dots)`} fill="#3bb75e">
        {dots.map((dot) => (
          <circle key={`${dot.x}-${dot.y}`} cx={dot.x} cy={dot.y} r="2.15" opacity="0.28" />
        ))}
      </g>
    </svg>
  )
}

export function Logo({ className, showTagline = false, inverted = false }: LogoProps) {
  const t = useT()
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <LogoMark className="h-8" />
      <span className="flex flex-col leading-none">
        <span className={cn('text-[17px] font-extrabold tracking-tight', inverted ? 'text-white' : 'text-navy')}>
          VoteTrace
        </span>
        {showTagline && (
          <span className={cn('mt-1 text-[11px]', inverted ? 'text-white/70' : 'text-muted-foreground')}>
            {t('Every Vote, Every Voice.')}
          </span>
        )}
      </span>
    </span>
  )
}
