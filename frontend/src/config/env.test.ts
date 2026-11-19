import { describe, expect, it } from 'vitest'
import { parseEnv } from '@/config/env'

describe('parseEnv', () => {
  it('applies safe defaults when nothing is configured', () => {
    const env = parseEnv({}, true)
    expect(env.apiBaseUrl).toBe('http://localhost:8000/api/v1')
    expect(env.isSupabaseConfigured).toBe(false)
    expect(env.adminPreviewEnabled).toBe(false)
  })

  it('treats empty strings as unset and strips trailing slashes', () => {
    const env = parseEnv({ VITE_API_BASE_URL: 'https://api.example.ng/api/v1/', VITE_SUPABASE_URL: '' }, false)
    expect(env.apiBaseUrl).toBe('https://api.example.ng/api/v1')
    expect(env.supabaseUrl).toBeUndefined()
  })

  it('never enables the admin preview outside dev builds', () => {
    expect(parseEnv({ VITE_ENABLE_ADMIN_PREVIEW: 'true' }, false).adminPreviewEnabled).toBe(false)
    expect(parseEnv({ VITE_ENABLE_ADMIN_PREVIEW: 'true' }, true).adminPreviewEnabled).toBe(true)
  })

  it('rejects malformed values', () => {
    expect(() => parseEnv({ VITE_API_BASE_URL: 'not-a-url' }, true)).toThrow(/VITE_API_BASE_URL/)
  })
})
