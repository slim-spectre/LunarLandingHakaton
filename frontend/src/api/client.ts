import { ApiClientError } from './errors'
import { isDemoModeEnabled, HEALTHY_FIXTURE } from './mocks'
import type { Health, ErrorEnvelope } from './types'

export interface ApiClientConfig {
  baseUrl?: string
  defaultTimeoutMs?: number
}

export interface RequestOptions {
  signal?: AbortSignal
  timeoutMs?: number
  headers?: Record<string, string>
}

/**
 * Normalizes the API base URL.
 * Falls back to import.meta.env.VITE_API_URL or 'http://localhost:8000'.
 */
export function resolveApiBaseUrl(overrideUrl?: string): string {
  const rawUrl =
    overrideUrl ??
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL
      ? import.meta.env.VITE_API_URL
      : 'http://localhost:8000')

  return rawUrl.trim().replace(/\/+$/, '')
}

export class ApiClient {
  readonly baseUrl: string
  readonly defaultTimeoutMs: number

  constructor(config?: ApiClientConfig) {
    this.baseUrl = resolveApiBaseUrl(config?.baseUrl)
    this.defaultTimeoutMs = config?.defaultTimeoutMs ?? 5000
  }

  /**
   * GET /api/v1/health
   *
   * Queries backend and PostgreSQL database health.
   * Does NOT fall back to synthetic data upon real failure.
   */
  async getHealth(options?: RequestOptions): Promise<Health> {
    // Explicit development mock mode (never runs in production; never triggers as error fallback)
    if (isDemoModeEnabled()) {
      return Promise.resolve({ ...HEALTHY_FIXTURE, timestamp: new Date().toISOString() })
    }

    const url = `${this.baseUrl}/api/v1/health`
    const timeoutMs = options?.timeoutMs ?? this.defaultTimeoutMs

    const controller = new AbortController()
    let timedOut = false

    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)

    // Chain caller's abort signal if provided
    if (options?.signal) {
      if (options.signal.aborted) {
        clearTimeout(timer)
        throw new ApiClientError({
          message: 'Request aborted by caller',
          code: 'REQUEST_ABORTED',
        })
      }
      options.signal.addEventListener('abort', () => {
        clearTimeout(timer)
        controller.abort()
      })
    }

    let response: Response
    try {
      response = await fetch(url, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          ...options?.headers,
        },
        signal: controller.signal,
      })
    } catch (err: unknown) {
      clearTimeout(timer)

      if (timedOut) {
        throw new ApiClientError({
          message: `Request timed out after ${timeoutMs}ms`,
          code: 'REQUEST_TIMEOUT',
          isTimeout: true,
          cause: err,
        })
      }

      if (options?.signal?.aborted) {
        throw new ApiClientError({
          message: 'Request aborted by caller',
          code: 'REQUEST_ABORTED',
          cause: err,
        })
      }

      throw new ApiClientError({
        message: 'Network unreachable: unable to connect to backend service',
        code: 'NETWORK_ERROR',
        isNetworkError: true,
        cause: err,
      })
    } finally {
      clearTimeout(timer)
    }

    // Inspect HTTP status code
    if (!response.ok) {
      let parsedEnvelope: ErrorEnvelope | undefined
      let requestId = response.headers.get('X-Request-ID') || undefined

      try {
        const body = await response.json()
        if (body && typeof body === 'object' && 'error' in body) {
          parsedEnvelope = body as ErrorEnvelope
          if (parsedEnvelope.error.request_id) {
            requestId = parsedEnvelope.error.request_id
          }
        }
      } catch {
        // Non-JSON error payload
      }

      const errorCode = parsedEnvelope?.error?.code ?? (response.status === 503 ? 'DATABASE_UNAVAILABLE' : `HTTP_${response.status}`)
      const errorMessage = parsedEnvelope?.error?.message ?? `API request failed with status ${response.status}`
      const details = parsedEnvelope?.error?.details ?? []

      throw new ApiClientError({
        message: errorMessage,
        statusCode: response.status,
        code: errorCode,
        details,
        requestId,
        rawEnvelope: parsedEnvelope,
      })
    }

    try {
      const data = (await response.json()) as Health
      return data
    } catch (err: unknown) {
      throw new ApiClientError({
        message: 'Invalid JSON response received from health endpoint',
        statusCode: response.status,
        code: 'INVALID_RESPONSE_FORMAT',
        cause: err,
      })
    }
  }
}

/**
 * Shared singleton instance of the API client.
 */
export const apiClient = new ApiClient()
