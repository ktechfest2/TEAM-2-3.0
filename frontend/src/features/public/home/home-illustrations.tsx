import type { LucideIcon } from 'lucide-react'

export function FeaturePhoto({ src, alt }: { src: string; alt: string }) {
  return (
    <figure className="overflow-hidden rounded-md bg-hero">
      <img src={src} alt={alt} width={1200} height={900} className="aspect-[4/3] h-auto w-full object-cover" />
    </figure>
  )
}

export function AudienceIcon({ icon: Icon }: { icon: LucideIcon; label?: string }) {
  return (
    <span className="mb-4 flex size-12 items-center justify-center rounded-[5px] bg-primary text-white" aria-hidden>
      <Icon className="size-6" strokeWidth={1.75} />
    </span>
  )
}
