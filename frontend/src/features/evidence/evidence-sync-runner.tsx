import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useAuth } from '@/features/auth/auth-context'
import { EVIDENCE_SUBMITTER_ROLES, hasAnyRole } from '@/features/auth/roles'
import { EVIDENCE_KEY } from '@/features/evidence/api'
import { startEvidenceSync } from '@/features/evidence/evidence-queue'

/** Uploads queued evidence while a submitter is signed in, including after reconnecting. */
export function EvidenceSyncRunner() {
  const { user, isPreview } = useAuth()
  const queryClient = useQueryClient()
  const canSubmit = Boolean(user && !isPreview && hasAnyRole(user.roles, EVIDENCE_SUBMITTER_ROLES))

  useEffect(() => {
    if (!canSubmit) return
    return startEvidenceSync(() => void queryClient.invalidateQueries({ queryKey: [EVIDENCE_KEY] }))
  }, [canSubmit, queryClient])

  return null
}
