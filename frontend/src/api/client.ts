import { ApiClientError } from './errors'
import { isDemoModeEnabled, HEALTHY_FIXTURE } from './mocks'
import type {
  Health,
  ErrorEnvelope,
  ApiError,
  SiteList,
  Site,
  JobAccepted,
  Job,
  NowRequest,
  NowResult,
  CSAResources,
  LayerList,
} from './types'

export interface ApiClientConfig {
  baseUrl?: string
  defaultTimeoutMs?: number
}

export interface RequestOptions {
  signal?: AbortSignal
  timeoutMs?: number
  headers?: Record<string, string>
}

export function resolveApiBaseUrl(overrideUrl?: string): string {
  return (
    overrideUrl ??
    import.meta.env.VITE_API_URL ??
    'http://localhost:8000'
  )
    .trim()
    .replace(/\/+$/, '')
}

function invalidResponse(
  message = 'The API returned an invalid response',
): never {
  throw new ApiClientError({ message, code: 'INVALID_RESPONSE_FORMAT' })
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function utc(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.endsWith('Z') &&
    Number.isFinite(Date.parse(value))
  )
}

function number(
  value: unknown,
  minimum: number,
  maximum: number,
): value is number {
  return (
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= minimum &&
    value <= maximum
  )
}

function apiError(value: unknown): value is ApiError {
  return (
    record(value) &&
    typeof value.code === 'string' &&
    typeof value.message === 'string' &&
    typeof value.request_id === 'string' &&
    Array.isArray(value.details) &&
    value.details.every(
      (detail) =>
        record(detail) &&
        typeof detail.field === 'string' &&
        typeof detail.reason === 'string',
    )
  )
}

function site(value: unknown): boolean {
  return (
    record(value) &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.description === 'string' &&
    typeof value.source_url === 'string' &&
    ['artemis', 'apollo', 'clps', 'international'].includes(
      String(value.category),
    ) &&
    number(value.latitude, -90, 90) &&
    number(value.longitude, -180, 180) &&
    value.longitude !== 180 &&
    (value.quickmap_url === null || typeof value.quickmap_url === 'string') &&
    (value.terrain_region_id === null ||
      typeof value.terrain_region_id === 'string')
  )
}

function body(value: unknown): boolean {
  return (
    record(value) &&
    number(value.azimuth_deg, 0, 360) &&
    value.azimuth_deg !== 360 &&
    number(value.elevation_deg, -90, 90) &&
    number(value.horizon_elevation_deg, -90, 90) &&
    typeof value.visible === 'boolean' &&
    record(value.direction_enu) &&
    ['east', 'north', 'up'].every((key) =>
      number((value.direction_enu as Record<string, unknown>)[key], -1, 1),
    )
  )
}

export class ApiClient {
  readonly baseUrl: string
  readonly defaultTimeoutMs: number

  constructor(config?: ApiClientConfig) {
    this.baseUrl = resolveApiBaseUrl(config?.baseUrl)
    this.defaultTimeoutMs = config?.defaultTimeoutMs ?? 5000
  }

  private async request<T>(
    path: string,
    options?: RequestOptions,
    payload?: NowRequest,
    expectedStatus = 200,
  ): Promise<T> {
    if (options?.signal?.aborted) {
      throw new ApiClientError({
        message: 'Request aborted by caller',
        code: 'REQUEST_ABORTED',
      })
    }
    const controller = new AbortController()
    const abort = () => controller.abort()
    options?.signal?.addEventListener('abort', abort, { once: true })
    let timedOut = false
    const timeoutMs = options?.timeoutMs ?? this.defaultTimeoutMs
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
    try {
      const response = await fetch(this.baseUrl + path, {
        method: payload ? 'POST' : 'GET',
        headers: {
          Accept: 'application/json',
          ...(payload ? { 'Content-Type': 'application/json' } : {}),
          ...options?.headers,
        },
        ...(payload ? { body: JSON.stringify(payload) } : {}),
        signal: controller.signal,
      })
      let data: unknown
      try {
        data = await response.json()
      } catch (error) {
        if (controller.signal.aborted) throw error
        if (response.ok)
          invalidResponse('Invalid JSON response received from the API')
      }
      if (!response.ok) {
        const envelope =
          record(data) && apiError(data.error)
            ? (data as ErrorEnvelope)
            : undefined
        const error = envelope?.error
        throw new ApiClientError({
          message:
            typeof error?.message === 'string'
              ? error.message
              : `API request failed with status ${response.status}`,
          code:
            typeof error?.code === 'string'
              ? error.code
              : `HTTP_${response.status}`,
          statusCode: response.status,
          details: Array.isArray(error?.details) ? error.details : [],
          requestId:
            error?.request_id ??
            response.headers.get('X-Request-ID') ??
            undefined,
          rawEnvelope: envelope,
        })
      }
      if (response.status !== expectedStatus)
        invalidResponse(
          `Expected HTTP ${expectedStatus}, received ${response.status}`,
        )
      return data as T
    } catch (error) {
      if (timedOut) {
        throw new ApiClientError({
          message: `Request timed out after ${timeoutMs}ms`,
          code: 'REQUEST_TIMEOUT',
          isTimeout: true,
          cause: error,
        })
      }
      if (options?.signal?.aborted) {
        throw new ApiClientError({
          message: 'Request aborted by caller',
          code: 'REQUEST_ABORTED',
          cause: error,
        })
      }
      if (error instanceof ApiClientError) throw error
      throw new ApiClientError({
        message: 'Network unreachable: unable to connect to backend service',
        code: 'NETWORK_ERROR',
        isNetworkError: true,
        cause: error,
      })
    } finally {
      clearTimeout(timer)
      options?.signal?.removeEventListener('abort', abort)
    }
  }

  async getHealth(options?: RequestOptions): Promise<Health> {
    if (isDemoModeEnabled())
      return { ...HEALTHY_FIXTURE, timestamp: new Date().toISOString() }
    const value = await this.request<Health>('/api/v1/health', options)
    if (
      value?.status !== 'healthy' ||
      value.service !== 'lunar-navigator-api' ||
      value.database !== 'ok' ||
      !utc(value.timestamp)
    )
      invalidResponse()
    return value
  }

  async getSites(
    filters: {
      category?: Site['category']
      limit?: number
      offset?: number
    } = {},
    options?: RequestOptions,
  ): Promise<SiteList> {
    const query = new URLSearchParams({
      limit: String(filters.limit ?? 50),
      offset: String(filters.offset ?? 0),
    })
    if (filters.category) query.set('category', filters.category)
    const value = await this.request<SiteList>(
      '/api/v1/sites?' + query,
      options,
    )
    if (
      !value ||
      !Array.isArray(value.items) ||
      !value.items.every(site) ||
      !Number.isInteger(value.total) ||
      value.total < 0 ||
      !Number.isInteger(value.limit) ||
      value.limit < 1 ||
      !Number.isInteger(value.offset) ||
      value.offset < 0
    )
      invalidResponse()
    return value
  }

  async submitNow(
    payload: NowRequest,
    options?: RequestOptions,
  ): Promise<JobAccepted> {
    const value = await this.request<JobAccepted>(
      '/api/v1/ephemeris/now',
      options,
      payload,
      202,
    )
    if (
      !value ||
      !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value.job_id) ||
      value.kind !== 'now' ||
      value.status !== 'queued' ||
      value.status_url !== `/api/v1/jobs/${value.job_id}` ||
      value.result_url !== `/api/v1/jobs/${value.job_id}/result`
    )
      invalidResponse()
    return value
  }

  private jobPath(path: string, result: boolean): string {
    const pattern =
      /^\/api\/v1\/jobs\/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(\/result)?$/i
    if (!pattern.test(path) || path.endsWith('/result') !== result)
      invalidResponse('The API returned an invalid job URL')
    return path
  }

  async getJob(statusUrl: string, options?: RequestOptions): Promise<Job> {
    const path = this.jobPath(statusUrl, false)
    const value = await this.request<Job>(path, options)
    if (
      !value ||
      value.kind !== 'now' ||
      value.job_id !== path.split('/').pop() ||
      !['queued', 'running', 'succeeded', 'failed'].includes(value.status) ||
      (value.status === 'failed' && !apiError(value.error))
    )
      invalidResponse()
    return value
  }

  async getResult(
    resultUrl: string,
    options?: RequestOptions,
  ): Promise<NowResult> {
    const value = await this.request<NowResult>(
      this.jobPath(resultUrl, true),
      options,
    )
    if (
      !value ||
      !record(value.site) ||
      typeof value.site.name !== 'string' ||
      !number(value.site.latitude, -90, 90) ||
      !number(value.site.longitude, -180, 180) ||
      value.site.longitude === 180 ||
      !number(value.site.observer_height_m, 0, 20) ||
      !Number.isFinite(value.site.surface_elevation_m) ||
      !record(value.point) ||
      !utc(value.point.timestamp) ||
      !body(value.point.sun) ||
      !body(value.point.earth) ||
      typeof value.point.is_golden_window !== 'boolean' ||
      !record(value.meta) ||
      typeof value.meta.model_version !== 'string' ||
      !utc(value.meta.generated_at) ||
      !['fresh', 'cached'].includes(value.meta.data_status) ||
      !['geometric', 'terrain'].includes(value.meta.horizon_mode) ||
      !Array.isArray(value.meta.sources) ||
      value.meta.sources.length === 0 ||
      !value.meta.sources.every(
        (source) =>
          record(source) &&
          typeof source.name === 'string' &&
          typeof source.url === 'string' &&
          (source.version === null || typeof source.version === 'string') &&
          utc(source.fetched_at),
      )
    )
      invalidResponse()
    return value
  }

  async getMapLayers(options?: RequestOptions): Promise<LayerList> {
    const value = await this.request<LayerList>('/api/v1/map/layers', options)
    if (
      !value ||
      !Array.isArray(value.items) ||
      !value.items.every(
        (layer) =>
          record(layer) &&
          typeof layer.id === 'string' &&
          typeof layer.name === 'string' &&
          typeof layer.attribution === 'string' &&
          typeof layer.source_url === 'string' &&
          ((layer.service_type === 'wmts' &&
            layer.id === 'LRO_WAC_Mosaic_Global_303ppd_v02' &&
            layer.crs_id === 'urn:ogc:def:crs:EPSG::104903' &&
            layer.tile_matrix_set === 'default028mm') ||
            (layer.service_type === 'wms' &&
              layer.crs_id === 'IAU2000:30100' &&
              layer.tile_matrix_set === null)) &&
          layer.coordinate_units === 'degrees' &&
          Array.isArray(layer.extent) &&
          layer.extent.length === 4 &&
          layer.extent.every(
            (v) => typeof v === 'number' && Number.isFinite(v),
          ) &&
          layer.extent[0] < layer.extent[2] &&
          layer.extent[1] < layer.extent[3] &&
          typeof layer.access_url_template === 'string' &&
          layer.access_url_template.startsWith(
            `/api/v1/map/layers/${layer.id}/`,
          ),
      )
    )
      invalidResponse('Unsupported or invalid lunar map metadata')
    return value
  }

  async getResources(options?: RequestOptions): Promise<CSAResources> {
    const value = await this.request<CSAResources>(
      '/api/v1/resources/csa?limit=10',
      { timeoutMs: 20000, ...options },
    )
    if (
      !value ||
      !['fresh', 'cached', 'stale'].includes(value.data_status) ||
      !utc(value.fetched_at) ||
      !Array.isArray(value.items) ||
      !value.items.every(
        (item) =>
          record(item) &&
          typeof item.id === 'string' &&
          typeof item.title === 'string' &&
          typeof item.summary === 'string' &&
          typeof item.url === 'string' &&
          utc(item.published_at) &&
          Array.isArray(item.topics) &&
          item.topics.every((topic) => typeof topic === 'string'),
      )
    )
      invalidResponse()
    return value
  }
}

export const apiClient = new ApiClient()
