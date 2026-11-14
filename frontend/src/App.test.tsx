import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { App } from './App'
import { apiClient } from './api/client'
import type { Health } from './api/types'

describe('App Shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders application title and baseline stage badge', () => {
    vi.spyOn(apiClient, 'getHealth').mockImplementation(() => new Promise(() => {}))
    render(<App />)

    expect(screen.getByTestId('app-title')).toHaveTextContent('Lunar Landing Site Navigator')
    expect(screen.getByText('Stage 0 Baseline')).toBeInTheDocument()
  })

  it('renders reserved areas for map, scene, and analytics', () => {
    vi.spyOn(apiClient, 'getHealth').mockImplementation(() => new Promise(() => {}))
    render(<App />)

    expect(screen.getByTestId('health-card')).toBeInTheDocument()
    expect(screen.getByTestId('map-slot')).toBeInTheDocument()
    expect(screen.getByTestId('scene-slot')).toBeInTheDocument()
    expect(screen.getByTestId('analytics-slot')).toBeInTheDocument()
  })

  it('ensures absence of fabricated operational or astronomical values', async () => {
    const mockHealth: Health = {
      status: 'healthy',
      service: 'lunar-navigator-api',
      timestamp: '2026-11-14T10:00:00Z',
      database: 'ok',
    }

    vi.spyOn(apiClient, 'getHealth').mockResolvedValue(mockHealth)

    const { container } = render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('status-badge')).toHaveTextContent('Healthy')
    })

    const textContent = container.textContent || ''

    // No invented golden windows, direct solar flux numbers, or fake comm windows
    expect(textContent).not.toMatch(/golden window:\s*\d+/i)
    expect(textContent).not.toMatch(/\d+\s*watts/i)
    expect(textContent).not.toMatch(/\d+\s*mbps/i)
    expect(textContent).toContain('Golden Windows: None (Awaiting Calculation)')
    expect(textContent).toContain('Sun Visibility: Uncomputed')
    expect(textContent).toContain('Earth Visibility: Uncomputed')
  })
})
