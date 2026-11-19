import { useNavigation } from 'react-router'

export function RouteProgress() {
  const navigation = useNavigation()
  if (navigation.state === 'idle') return null
  return (
    <div role="progressbar" aria-label="Loading page" className="fixed inset-x-0 top-0 z-[60] h-0.5 overflow-hidden">
      <div className="h-full w-1/3 animate-pulse bg-primary" />
    </div>
  )
}
