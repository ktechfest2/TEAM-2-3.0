import { env } from '@/config/env'

/** Error envelope returned by the FastAPI backend (see backend/app/core/errors.py). */
export type ApiErrorBody = {
  error: {
    code: string
    message: string
    request_id?: string
    details?: unknown
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | undefined
  readonly details: unknown

  constructor(status: number, code: string, message: string, requestId?: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

type TokenProvider = () => Promise<string | null>

let getAccessToken: TokenProvider = async () => null

let onUnauthorized: () => void = () => {}

/** Registered by the auth layer so requests carry the current access token. */
export function setAccessTokenProvider(provider: TokenProvider) {
  getAccessToken = provider
}

/** Called when the server rejects the token we sent, so the session can be cleared. */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  /** Attach the bearer token. Defaults to true. */
  auth?: boolean
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as ApiErrorBody).error?.message === 'string'
  )
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, headers, ...init } = options
  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')

  if (body !== undefined && !(body instanceof FormData)) {
    requestHeaders.set('Content-Type', 'application/json')
  }
  let sentToken = false
  if (auth) {
    const token = await getAccessToken()
    if (token) {
      requestHeaders.set('Authorization', `Bearer ${token}`)
      sentToken = true
    }
  }

  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      headers: requestHeaders,
      credentials: 'omit',
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Unable to reach the VoteTrace server. Check your connection.')
  }

  if (response.status === 204) return undefined as T

  const payload: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    if (response.status === 401 && sentToken) onUnauthorized()
    if (isApiErrorBody(payload)) {
      const { code, message, request_id, details } = payload.error
      throw new ApiError(response.status, code, message, request_id, details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed with status ${response.status}`)
  }

  return payload as T
}

/** Fetch an authenticated binary resource (for example a private evidence image). */
export async function apiBlob(path: string): Promise<{ blob: Blob; sha256: string | null }> {
  const headers = new Headers()
  const token = await getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, { headers, credentials: 'omit', cache: 'no-store' })
  } catch {
    throw new ApiError(0, 'network_error', 'Unable to reach the VoteTrace server. Check your connection.')
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null)
    if (isApiErrorBody(payload)) {
      const { code, message, request_id, details } = payload.error
      throw new ApiError(response.status, code, message, request_id, details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed with status ${response.status}`)
  }
  return { blob: await response.blob(), sha256: response.headers.get('X-Content-SHA256') }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: 'DELETE' }),
}
