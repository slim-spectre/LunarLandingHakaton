import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '../../api/client'
import { ApiClientError } from '../../api/errors'
import { isDemoModeEnabled } from '../../api/mocks'
import type { Health } from '../../api/types'

export type HealthStatus =
  | 'loading'
  | 'healthy'
  | 'database_unavailable'
  | 'network_unreachable'
  | 'error'

export interface UseHealthResult {
  status: HealthStatus
  health: Health | null
  error: ApiClientError | null
  isDemoMode: boolean
  refresh: () => Promise<void>
}

/**
 * Hook to manage backend health state.
 *
 * Rules:
 * - Initial state must be 'loading'.
 * - Never invents health values if the backend fails.
 */
export function useHealth(): UseHealthResult {
  const [status, setStatus] = useState<HealthStatus>('loading')
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<ApiClientError | null>(null)
  const demoActive = isDemoModeEnabled()

  const refresh = useCallback(async () => {
    setStatus('loading')
    setError(null)

    try {
      const data = await apiClient.getHealth()
      setHealth(data)
      setStatus('healthy')
    } catch (err: unknown) {
      setHealth(null)
      if (err instanceof ApiClientError) {
        setError(err)
        if (err.isDatabaseUnavailable) {
          setStatus('database_unavailable')
        } else if (err.isNetworkError || err.isTimeout) {
          setStatus('network_unreachable')
        } else {
          setStatus('error')
        }
      } else {
        const fallbackError = new ApiClientError({
          message: err instanceof Error ? err.message : 'Unknown health check failure',
          cause: err,
        })
        setError(fallbackError)
        setStatus('error')
      }
    }
  }, [])

  useEffect(() => {
    let active = true

    apiClient
      .getHealth()
      .then((data) => {
        if (active) {
          setHealth(data)
          setStatus('healthy')
        }
      })
      .catch((err: unknown) => {
        if (!active) return
        setHealth(null)
        if (err instanceof ApiClientError) {
          setError(err)
          if (err.isDatabaseUnavailable) {
            setStatus('database_unavailable')
          } else if (err.isNetworkError || err.isTimeout) {
            setStatus('network_unreachable')
          } else {
            setStatus('error')
          }
        } else {
          setError(
            new ApiClientError({
              message: err instanceof Error ? err.message : 'Unknown health check failure',
              cause: err,
            }),
          )
          setStatus('error')
        }
      })

    return () => {
      active = false
    }
  }, [])

  return {
    status,
    health,
    error,
    isDemoMode: demoActive,
    refresh,
  }
}
