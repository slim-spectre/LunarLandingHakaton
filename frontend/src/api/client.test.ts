import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiClient, resolveApiBaseUrl } from './client'
import { ApiClientError } from './errors'
import type { Health, ErrorEnvelope } from './types'

describe('ApiClient Base URL Resolution', () => {
  it('correctly reads override base URL and strips trailing slashes', () => {
    expect(resolveApiBaseUrl('http://api.lunar.test/')).toBe('http://api.lunar.test')
    expect(resolveApiBaseUrl('http://api.lunar.test///')).toBe('http://api.lunar.test')
    expect(resolveApiBaseUrl('https://custom.endpoint:8443')).toBe('https://custom.endpoint:8443')
  })

  it('defaults to http://localhost:8000 when no environment or override is provided', () => {
    const originalEnv = import.meta.env.VITE_API_URL
    delete (import.meta.env as Record<string, unknown>).VITE_API_URL

    const url = resolveApiBaseUrl()
    expect(url).toBe('http://localhost:8000')

    if (originalEnv !== undefined) {
      ;(import.meta.env as Record<string, unknown>).VITE_API_URL = originalEnv
    }
  })
})

describe('ApiClient Health Request', () => {
  let client: ApiClient
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    client = new ApiClient({ baseUrl: 'http://backend.test:8000', defaultTimeoutMs: 1000 })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('handles health HTTP 200 response with correct contract fields', async () => {
    const mockHealth: Health = {
      status: 'healthy',
      service: 'lunar-navigator-api',
      timestamp: '2026-11-14T10:00:00Z',
      database: 'ok',
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockHealth,
      headers: new Headers(),
    } as unknown as Response)

    const result = await client.getHealth()

    expect(result).toEqual(mockHealth)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://backend.test:8000/api/v1/health',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Accept: 'application/json' }),
      }),
    )
  })

  it('parses the agreed HTTP 503 database unavailable error envelope', async () => {
    const mockDbError: ErrorEnvelope = {
      error: {
        code: 'DATABASE_UNAVAILABLE',
        message: 'Database is unavailable',
        details: [],
        request_id: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
      },
    }

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => mockDbError,
      headers: new Headers({ 'X-Request-ID': 'a706df04-b7c9-49c0-8eea-b53c71f86fe8' }),
    } as unknown as Response)

    await expect(client.getHealth()).rejects.toThrow(ApiClientError)

    try {
      await client.getHealth()
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError)
      const apiErr = err as ApiClientError
      expect(apiErr.statusCode).toBe(503)
      expect(apiErr.code).toBe('DATABASE_UNAVAILABLE')
      expect(apiErr.message).toBe('Database is unavailable')
      expect(apiErr.requestId).toBe('a706df04-b7c9-49c0-8eea-b53c71f86fe8')
      expect(apiErr.isDatabaseUnavailable).toBe(true)
      expect(apiErr.isNetworkError).toBe(false)
    }
  })

  it('handles network failure without synthetic fallback', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(client.getHealth()).rejects.toThrow(ApiClientError)

    try {
      await client.getHealth()
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError)
      const apiErr = err as ApiClientError
      expect(apiErr.isNetworkError).toBe(true)
      expect(apiErr.code).toBe('NETWORK_ERROR')
      expect(apiErr.statusCode).toBe(0)
      expect(apiErr.message).toContain('Network unreachable')
    }
  })

  it('handles request timeout explicitly', async () => {
    // Simulate abort via timeout
    globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
      return new Promise((_resolve, reject) => {
        const signal = options?.signal as AbortSignal
        signal.addEventListener('abort', () => {
          const abortError = new Error('The operation was aborted')
          abortError.name = 'AbortError'
          reject(abortError)
        })
      })
    })

    const shortTimeoutClient = new ApiClient({
      baseUrl: 'http://backend.test:8000',
      defaultTimeoutMs: 50,
    })

    try {
      await shortTimeoutClient.getHealth()
      expect.fail('Should have timed out')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiClientError)
      const apiErr = err as ApiClientError
      expect(apiErr.isTimeout).toBe(true)
      expect(apiErr.code).toBe('REQUEST_TIMEOUT')
    }
  })

  it('respects caller abort signal', async () => {
    const controller = new AbortController()
    controller.abort()

    await expect(client.getHealth({ signal: controller.signal })).rejects.toThrow(
      'Request aborted by caller',
    )
  })
})
