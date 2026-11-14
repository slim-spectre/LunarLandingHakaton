import type { ErrorEnvelope, ErrorDetail } from './types'

export interface ApiClientErrorOptions {
  message: string
  statusCode?: number
  code?: string
  details?: ErrorDetail[]
  requestId?: string
  isNetworkError?: boolean
  isTimeout?: boolean
  rawEnvelope?: ErrorEnvelope
  cause?: unknown
}

/**
 * Standardized client error encapsulating the API v1 error envelope or transport failure.
 *
 * Adheres strictly to the agreed error schema:
 * {
 *   "error": {
 *     "code": string,
 *     "message": string,
 *     "details": ErrorDetail[],
 *     "request_id": string
 *   }
 * }
 */
export class ApiClientError extends Error {
  readonly statusCode: number
  readonly code: string
  readonly details: ErrorDetail[]
  readonly requestId?: string
  readonly isNetworkError: boolean
  readonly isTimeout: boolean
  readonly rawEnvelope?: ErrorEnvelope

  constructor(options: ApiClientErrorOptions) {
    super(options.message)
    this.name = 'ApiClientError'
    this.statusCode = options.statusCode ?? 0
    this.code =
      options.code ??
      (options.isNetworkError
        ? 'NETWORK_ERROR'
        : options.isTimeout
          ? 'REQUEST_TIMEOUT'
          : options.statusCode
            ? `HTTP_${options.statusCode}`
            : 'UNKNOWN_ERROR')
    this.details = options.details ?? []
    this.requestId = options.requestId
    this.isNetworkError = Boolean(options.isNetworkError)
    this.isTimeout = Boolean(options.isTimeout)
    this.rawEnvelope = options.rawEnvelope

    if (options.cause) {
      this.cause = options.cause
    }
  }

  /**
   * True if this represents a 503 DATABASE_UNAVAILABLE failure.
   */
  get isDatabaseUnavailable(): boolean {
    return this.code === 'DATABASE_UNAVAILABLE'
  }
}
