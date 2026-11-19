import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const alertVariants = cva(
  'relative grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 rounded-lg border px-4 py-3 text-sm [&>svg]:mt-0.5 [&>svg]:size-4',
  {
    variants: {
      variant: {
        default: 'border-border bg-card text-foreground [&>svg]:text-muted-foreground',
        info: 'border-info/20 bg-info-subtle text-foreground [&>svg]:text-info',
        success: 'border-success/20 bg-success-subtle text-foreground [&>svg]:text-success',
        warning: 'border-warning/25 bg-warning-subtle text-foreground [&>svg]:text-warning',
        destructive: 'border-destructive/20 bg-destructive-subtle text-foreground [&>svg]:text-destructive',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

function Alert({ className, variant, ...props }: ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
  return <div data-slot="alert" role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

function AlertTitle({ className, ...props }: ComponentProps<'div'>) {
  return <div data-slot="alert-title" className={cn('col-start-2 font-medium', className)} {...props} />
}

function AlertDescription({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div data-slot="alert-description" className={cn('col-start-2 text-muted-foreground', className)} {...props} />
  )
}

export { Alert, AlertDescription, AlertTitle }
