import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from './client'
import {
  accepted,
  catalog,
  observationResult,
  request,
  resources,
  resourceItem,
  succeeded,
} from '../test/fixtures'

describe('Stage 1 API transport', () => {
  const client = new ApiClient({ baseUrl: 'http://backend.test' })
  const fetch = vi.fn()
  const respond = (body: unknown, status = 200) =>
    fetch.mockResolvedValueOnce(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  beforeEach(() => {
    fetch.mockReset()
    vi.stubGlobal('fetch', fetch)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('submits the exclusive site form as JSON and requires HTTP 202', async () => {
    respond(accepted, 202)
    expect(await client.submitNow(request)).toEqual(accepted)
    expect(fetch).toHaveBeenCalledWith(
      'http://backend.test/api/v1/ephemeris/now',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(request),
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    )
    respond(accepted, 200)
    await expect(client.submitNow(request)).rejects.toMatchObject({
      code: 'INVALID_RESPONSE_FORMAT',
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('loads catalog filters and pagination without adding computed percentages', async () => {
    respond(catalog)
    expect(
      await client.getSites({ category: 'artemis', limit: 50, offset: 50 }),
    ).toEqual(catalog)
    expect(fetch.mock.calls[0][0]).toBe(
      'http://backend.test/api/v1/sites?limit=50&offset=50&category=artemis',
    )
    expect(catalog.items[0]).not.toHaveProperty('illumination_percent')
  })
  it('uses the returned relative job URLs and reads an observation result', async () => {
    respond(succeeded)
    expect(await client.getJob(accepted.status_url)).toEqual(succeeded)
    respond(observationResult)
    expect(await client.getResult(accepted.result_url)).toEqual(
      observationResult,
    )
    await expect(
      client.getJob('https://untrusted.example/api/v1/jobs/' + accepted.job_id),
    ).rejects.toMatchObject({ code: 'INVALID_RESPONSE_FORMAT' })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it.each([
    [404, 'JOB_NOT_FOUND'],
    [410, 'JOB_EXPIRED'],
    [422, 'TERRAIN_UNAVAILABLE'],
    [409, 'JOB_NOT_READY'],
  ])('preserves HTTP %i %s and request ID', async (status, code) => {
    respond(
      {
        error: {
          code,
          message: 'Controlled failure',
          details: [{ field: 'site', reason: 'test' }],
          request_id: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
        },
      },
      status,
    )
    await expect(client.getResult(accepted.result_url)).rejects.toMatchObject({
      code,
      statusCode: status,
      requestId: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
      details: [{ field: 'site', reason: 'test' }],
    })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('never turns a source failure into a database error or synthetic resources', async () => {
    respond(
      {
        error: {
          code: 'SOURCE_UNAVAILABLE',
          message: 'Unavailable',
          details: [],
          request_id: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
        },
      },
      503,
    )
    await expect(client.getResources()).rejects.toMatchObject({
      code: 'SOURCE_UNAVAILABLE',
      isDatabaseUnavailable: false,
    })
    respond(resources)
    expect(await client.getResources()).toEqual(resources)
  })
  it('rejects incomplete scientific results and malformed feed dates', async () => {
    respond({
      ...observationResult,
      point: { ...observationResult.point, earth: { visible: true } },
    })
    await expect(client.getResult(accepted.result_url)).rejects.toMatchObject({
      code: 'INVALID_RESPONSE_FORMAT',
    })
    respond({
      ...resources,
      items: [{ ...resourceItem, published_at: 'invalid' }],
    })
    await expect(client.getResources()).rejects.toMatchObject({
      code: 'INVALID_RESPONSE_FORMAT',
    })
  })

  it('does not render untrusted objects from malformed error details', async () => {
    respond({ error: { code: 'SOURCE_UNAVAILABLE', message: 'Invalid envelope', details: [{ field: 'site', reason: { html: 'untrusted' } }], request_id: accepted.job_id } }, 503)
    await expect(client.getResources()).rejects.toMatchObject({ code: 'HTTP_503', details: [] })
  })
  it('keeps abort and timeout active while consuming the response body', async () => {
    fetch.mockImplementationOnce((_url, options: RequestInit) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          new Promise((_resolve, reject) => {
            options.signal!.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            )
          }),
      }),
    )
    await expect(client.getResources({ timeoutMs: 20 })).rejects.toMatchObject({
      code: 'REQUEST_TIMEOUT',
    })
    const controller = new AbortController()
    const remove = vi.spyOn(controller.signal, 'removeEventListener')
    respond(resources)
    await client.getResources({ signal: controller.signal })
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
  })
})
