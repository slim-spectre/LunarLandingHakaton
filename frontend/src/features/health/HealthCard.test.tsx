import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HealthCard } from './HealthCard'
import { apiClient } from '../../api/client'
import { ApiClientError } from '../../api/errors'
import type { Health } from '../../api/types'

describe('HealthCard Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders initial loading state before network response arrives', () => {
    // Return pending promise
    vi.spyOn(apiClient, 'getHealth').mockImplementation(() => new Promise(() => {}))

    render(<HealthCard />)

    expect(screen.getByTestId('status-badge')).toHaveTextContent('Checking...')
    expect(screen.getByTestId('state-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('state-healthy')).not.toBeInTheDocument()
    expect(screen.queryByTestId('state-database-unavailable')).not.toBeInTheDocument()
  })

  it('displays healthy status and contract fields on HTTP 200 response', async () => {
    const mockHealth: Health = {
      status: 'healthy',
      service: 'lunar-navigator-api',
      timestamp: '2027-07-15T00:00:00Z',
      database: 'ok',
    }

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue(mockHealth)

    render(<HealthCard />)

    await waitFor(() => {
      expect(screen.getByTestId('status-badge')).toHaveTextContent('Healthy')
    })

    expect(screen.getByText('lunar-navigator-api')).toBeInTheDocument()
    expect(screen.getByText('ok')).toBeInTheDocument()
    expect(screen.getByText('2027-07-15T00:00:00Z')).toBeInTheDocument()
  })

  it('displays database unavailable error details on HTTP 503 failure', async () => {
    const dbError = new ApiClientError({
      message: 'Database is unavailable',
      statusCode: 503,
      code: 'DATABASE_UNAVAILABLE',
      requestId: 'a706df04-b7c9-49c0-8eea-b53c71f86fe8',
    })

    vi.spyOn(apiClient, 'getHealth').mockRejectedValue(dbError)

    render(<HealthCard />)

    await waitFor(() => {
      expect(screen.getByTestId('status-badge')).toHaveTextContent('DB Unavailable')
    })

    expect(screen.getByTestId('state-database-unavailable')).toBeInTheDocument()
    expect(screen.getByText('DATABASE_UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText('a706df04-b7c9-49c0-8eea-b53c71f86fe8')).toBeInTheDocument()
    expect(screen.getByText('Database is unavailable')).toBeInTheDocument()
  })

  it('displays network unreachable state on network connection failure', async () => {
    const networkError = new ApiClientError({
      message: 'Network unreachable: unable to connect to backend service',
      isNetworkError: true,
      code: 'NETWORK_ERROR',
    })

    vi.spyOn(apiClient, 'getHealth').mockRejectedValue(networkError)

    render(<HealthCard />)

    await waitFor(() => {
      expect(screen.getByTestId('status-badge')).toHaveTextContent('Network Unreachable')
    })

    expect(screen.getByTestId('state-network-unreachable')).toBeInTheDocument()
    expect(screen.getByText('NETWORK_ERROR')).toBeInTheDocument()
    expect(screen.getByTestId('refresh-button')).not.toBeDisabled()
  })
})
