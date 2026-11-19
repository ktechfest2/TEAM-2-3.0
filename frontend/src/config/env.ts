import * as z from 'zod/mini'

const envSchema = z.object({
  VITE_API_BASE_URL: z._default(z.url(), 'http://localhost:8000/api/v1'),
  VITE_SUPABASE_URL: z.optional(z.url()),
  VITE_SUPABASE_ANON_KEY: z.optional(z.string().check(z.minLength(20))),
  VITE_APP_ENV: z._default(z.enum(['development', 'staging', 'production']), 'development'),
  VITE_ENABLE_ADMIN_PREVIEW: z._default(z.enum(['true', 'false']), 'false'),
})

export type AppEnv = {
  apiBaseUrl: string
  supabaseUrl: string | undefined
  supabaseAnonKey: string | undefined
  appEnv: 'development' | 'staging' | 'production'
  isSupabaseConfigured: boolean
  /** Admin UI preview without auth. Only ever true in Vite dev builds. */
  adminPreviewEnabled: boolean
}

/** Empty strings in .env files mean "unset". */
function withoutEmptyValues(raw: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(raw).filter(([, value]) => value !== ''))
}

export function parseEnv(raw: Record<string, unknown>, isDevBuild: boolean): AppEnv {
  const result = envSchema.safeParse(withoutEmptyValues(raw))
  if (!result.success) {
    const issues = result.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`)
    throw new Error(`Invalid frontend environment configuration:\n${issues.join('\n')}`)
  }
  const parsed = result.data
  return {
    apiBaseUrl: parsed.VITE_API_BASE_URL.replace(/\/+$/, ''),
    supabaseUrl: parsed.VITE_SUPABASE_URL,
    supabaseAnonKey: parsed.VITE_SUPABASE_ANON_KEY,
    appEnv: parsed.VITE_APP_ENV,
    isSupabaseConfigured: Boolean(parsed.VITE_SUPABASE_URL && parsed.VITE_SUPABASE_ANON_KEY),
    adminPreviewEnabled: isDevBuild && parsed.VITE_ENABLE_ADMIN_PREVIEW === 'true',
  }
}

export const env = parseEnv(import.meta.env, import.meta.env.DEV)
