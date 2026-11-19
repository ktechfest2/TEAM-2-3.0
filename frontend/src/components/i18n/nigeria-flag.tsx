import { cn } from '@/lib/utils'

export function NigeriaFlag({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 6 4"
      className={cn('block h-4 w-6 overflow-hidden rounded-[2px] ring-1 ring-navy/15', className)}
      aria-hidden
    >
      <rect width="2" height="4" fill="#008751" />
      <rect x="2" width="2" height="4" fill="#ffffff" />
      <rect x="4" width="2" height="4" fill="#008751" />
    </svg>
  )
}
