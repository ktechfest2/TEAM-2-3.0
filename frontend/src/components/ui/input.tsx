import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const fieldBase =
  'w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm text-foreground shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring/30 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:outline-destructive/30'

function Input({ className, type = 'text', ...props }: ComponentProps<'input'>) {
  return <input data-slot="input" type={type} className={cn(fieldBase, 'h-10 py-2', className)} {...props} />
}

function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea data-slot="textarea" className={cn(fieldBase, 'min-h-24 py-2', className)} {...props} />
}

function Select({ className, ...props }: ComponentProps<'select'>) {
  return <select data-slot="select" className={cn(fieldBase, 'h-10 py-2 pr-8', className)} {...props} />
}

export { Input, Select, Textarea }
