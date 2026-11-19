import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-accent text-accent-foreground',
        neutral: 'border-border bg-muted text-muted-foreground',
        success: 'border-success/20 bg-success-subtle text-success',
        warning: 'border-warning/20 bg-warning-subtle text-warning',
        destructive: 'border-destructive/20 bg-destructive-subtle text-destructive',
        info: 'border-info/20 bg-info-subtle text-info',
        outline: 'border-border text-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

type BadgeProps = ComponentProps<'span'> & VariantProps<typeof badgeVariants>

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
