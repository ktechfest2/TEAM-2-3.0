import type { Session } from '@supabase/supabase-js'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { env } from '@/config/env'
import { setAccessTokenProvider, setUnauthorizedHandler } from '@/lib/api-client'
import { getSupabase } from '@/lib/supabase'
import { AuthContext, type AuthState, type AuthUser } from '@/features/auth/auth-context'
import * as local from '@/features/auth/local-session'
import { ROLES, rolesFromAppMetadata } from '@/features/auth/roles'

const PREVIEW_USER: AuthUser = { id: 'preview', email: 'preview@localhost', roles: [...ROLES] }

function toAuthUser(session: Session | null): AuthUser | null {
  if (!session) return null
  return {
    id: session.user.id,
    email: session.user.email ?? null,
    roles: rolesFromAppMetadata(session.user.app_metadata),
  }
}

/** Supabase when a project is configured; otherwise VoteTrace's built-in accounts. */
export function AuthProvider({ children }: { children: ReactNode }) {
  return env.isSupabaseConfigured ? (
    <SupabaseAuthProvider>{children}</SupabaseAuthProvider>
  ) : (
    <LocalAuthProvider>{children}</LocalAuthProvider>
  )
}

function LocalAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<local.StoredSession | null>(() => local.readStoredSession())
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(() => local.readStoredSession() !== null)

  const clear = useCallback(() => {
    local.storeSession(null)
    setSession(null)
    setUser(null)
  }, [])

  useEffect(() => {
    setAccessTokenProvider(async () => local.readStoredSession()?.token ?? null)
    setUnauthorizedHandler(clear)
  }, [clear])

  useEffect(() => {
    if (!session || user) return
    let cancelled = false
    local
      .fetchPrincipal()
      .then((principal) => {
        if (!cancelled) setUser(principal)
      })
      .catch(() => {
        if (!cancelled) clear()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [session, user, clear])

  useEffect(() => {
    if (!session) return
    const remaining = Date.parse(session.expiresAt) - Date.now()
    const timer = window.setTimeout(clear, Math.max(0, Math.min(remaining, 2 ** 31 - 1)))
    return () => window.clearTimeout(timer)
  }, [session, clear])

  const value = useMemo<AuthState>(() => {
    const isPreview = !session && env.adminPreviewEnabled
    const current = isPreview ? PREVIEW_USER : user
    const accept = (response: local.SessionResponse) => {
      const next = { token: response.access_token, expiresAt: response.expires_at }
      local.storeSession(next)
      const signedIn = local.userFromAccount(response.account)
      setSession(next)
      setUser(signedIn)
      setLoading(false)
      return signedIn
    }
    return {
      status: loading ? 'loading' : current ? 'authenticated' : 'anonymous',
      user: current,
      isPreview,
      isConfigured: true,
      provider: 'local',
      async signInWithPassword(email, password) {
        return accept(await local.signIn(email, password))
      },
      async changePassword(currentPassword, newPassword) {
        accept(await local.changePassword(currentPassword, newPassword))
      },
      async signOut() {
        clear()
      },
    }
  }, [session, user, loading, clear])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

function SupabaseAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let unsubscribe: (() => void) | undefined
    let cancelled = false

    void getSupabase().then(async (client) => {
      if (!client || cancelled) return
      setAccessTokenProvider(async () => {
        const { data } = await client.auth.getSession()
        return data.session?.access_token ?? null
      })
      const { data } = await client.auth.getSession()
      if (cancelled) return
      setSession(data.session)
      setLoading(false)
      const { data: listener } = client.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession))
      unsubscribe = () => listener.subscription.unsubscribe()
    })

    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [])

  const value = useMemo<AuthState>(() => {
    const user = toAuthUser(session)
    return {
      status: loading ? 'loading' : user ? 'authenticated' : 'anonymous',
      user,
      isPreview: false,
      isConfigured: true,
      provider: 'supabase',
      async signInWithPassword(email, password) {
        const client = await getSupabase()
        if (!client) throw new Error('Authentication is not configured for this environment.')
        const { data, error } = await client.auth.signInWithPassword({ email, password })
        if (error || !data.session) throw new Error('Sign-in failed. Check your credentials and try again.')
        return toAuthUser(data.session) as AuthUser
      },
      async signOut() {
        const client = await getSupabase()
        if (client) await client.auth.signOut()
      },
    }
  }, [session, loading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
