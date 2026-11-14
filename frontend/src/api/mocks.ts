import type { Health, ErrorEnvelope } from './types'

/**
 * Agreed synthetic development fixtures from contracts/examples/.
 * These are strictly development fixtures and never measured scientific results.
 */
export const HEALTHY_FIXTURE: Health = {
  status: 'healthy',
  service: 'lunar-navigator-api',
  timestamp: '2027-07-15T00:00:00Z',
  database: 'ok',
}

export const DATABASE_UNAVAILABLE_FIXTURE: ErrorEnvelope = {
  error: {
    code: 'DATABASE_UNAVAILABLE',
    message: 'Database is unavailable',
    details: [],
    request_id: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
  },
}

/**
 * Determines whether demo/mock mode is explicitly enabled.
 *
 * Rules:
 * - Disabled by default.
 * - Only possible when import.meta.env.DEV is true (never in production builds).
 * - Requires explicit VITE_USE_CONTRACT_MOCKS === 'true' environment flag or runtime query param ?demo=true in dev.
 * - Must never automatically activate as a fallback when real backend calls fail.
 */
export function isDemoModeEnabled(): boolean {
  if (!import.meta.env.DEV) {
    return false
  }

  // Explicit env variable:
  if (import.meta.env.VITE_USE_CONTRACT_MOCKS === 'true') {
    return true
  }

  // Explicit dev query parameter:
  if (typeof window !== 'undefined' && window.location?.search) {
    const params = new URLSearchParams(window.location.search)
    return params.get('demo') === 'true'
  }

  return false
}
