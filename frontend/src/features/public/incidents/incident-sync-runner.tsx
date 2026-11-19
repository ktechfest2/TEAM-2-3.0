import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { draftKeys, startIncidentSync } from '@/features/public/incidents/drafts'

/** Sends incident reports saved offline once the device is back online. */
export function IncidentSyncRunner() {
  const queryClient = useQueryClient()
  useEffect(() => startIncidentSync(() => void queryClient.invalidateQueries({ queryKey: draftKeys.all })), [queryClient])
  return null
}
