import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, setAccessTokenProvider } from '@/lib/api-client'

function mockFetch(response: Response | Error) {
  const fn = vi.fn(() => (response instanceof Error ? Promise.reject(response) : Promise.resolve(response)))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessTokenProvider(async () => null)
})

describe('api client', () => {
  it('attaches the bearer token when available', async () => {
    setAccessTokenProvider(async () => 'token-123')
    const fetchMock = mockFetch(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await expect(api.get('/auth/me')).resolves.toEqual({ ok: true })

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/api/v1/auth/me')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer token-123')
    expect(init.credentials).toBe('omit')
  })

  it('omits the token for unauthenticated requests', async () => {
    setAccessTokenProvider(async () => 'token-123')
    const fetchMock = mockFetch(new Response('{}', { status: 200 }))
    await api.get('/health', { auth: false })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
  })

  it('maps the backend error envelope to ApiError', async () => {
    mockFetch(
      new Response(JSON.stringify({ error: { code: 'forbidden', message: 'Insufficient role', request_id: 'r1' } }), {
        status: 403,
      }),
    )
    const error = await api.get('/admin/thing').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 403, code: 'forbidden', requestId: 'r1' })
  })

  it('reports network failures distinctly', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    await expect(api.get('/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })
})
