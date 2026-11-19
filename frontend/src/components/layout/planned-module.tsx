import { ConstructionIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

type PlannedModuleProps = {
  /** Capabilities this module will deliver once implemented. */
  capabilities: string[]
  note?: string
}

/**
 * Honest placeholder for modules that are scaffolded but not yet built.
 * Never render fabricated data in its place.
 */
export function PlannedModule({ capabilities, note }: PlannedModuleProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2">
          <ConstructionIcon className="size-4 text-muted-foreground" aria-hidden />
          Planned capabilities
        </CardTitle>
        <Badge variant="neutral">Not yet available</Badge>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
          {capabilities.map((capability) => (
            <li key={capability} className="flex gap-2">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" aria-hidden />
              <span>{capability}</span>
            </li>
          ))}
        </ul>
        {note && <p className="mt-4 border-t pt-4 text-xs text-muted-foreground">{note}</p>}
      </CardContent>
    </Card>
  )
}
