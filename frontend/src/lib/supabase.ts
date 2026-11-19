import type { SupabaseClient } from '@supabase/supabase-js'
import { env } from '@/config/env'

let clientPromise: Promise<SupabaseClient | null> | undefined

/**
 * Lazily creates the browser Supabase client so the SDK is not part of the
 * initial public bundle. Uses ONLY the public anon key; all data access is
 * constrained by Row Level Security and the FastAPI backend. The service-role
 * key must never be referenced anywhere in the frontend.
 */
export function getSupabase(): Promise<SupabaseClient | null> {
  if (!env.supabaseUrl || !env.supabaseAnonKey) return Promise.resolve(null)
  const url = env.supabaseUrl
  const anonKey = env.supabaseAnonKey
  clientPromise ??= import('@supabase/supabase-js').then(({ createClient }) =>
    createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: 'pkce',
      },
    }),
  )
  return clientPromise
}
