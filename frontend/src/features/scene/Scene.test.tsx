import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import { SceneErrorBoundary } from './SceneErrorBoundary'
import { LunarScene } from './LunarScene'
import { enuToLocalScene, azimuthElevationToEnu } from '../../lib/coordinates'
import type { ObservationPoint } from './types'

// Polyfill ResizeObserver for jsdom environment
beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

afterAll(() => {
  delete (globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver
})

// Component that throws to simulate a WebGL context failure or shader compilation crash
const BrokenWebGLComponent: React.FC = () => {
  throw new Error('Simulated WebGL context creation failed: WEBGL_UNSUPPORTED')
}

describe('Scene Error Isolation (SceneErrorBoundary)', () => {
  it('renders children when no error occurs', () => {
    render(
      <SceneErrorBoundary>
        <div data-testid="scene-child">Healthy Scene Content</div>
      </SceneErrorBoundary>
    )

    expect(screen.getByTestId('scene-child')).toBeInTheDocument()
    expect(screen.queryByTestId('scene-error-fallback')).not.toBeInTheDocument()
  })

  it('catches WebGL errors, isolates them, and renders local fallback message without crashing', () => {
    const handleError = vi.fn()
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <div>
        <div data-testid="app-shell-header">App Shell Header Is Intact</div>
        <SceneErrorBoundary onError={handleError}>
          <BrokenWebGLComponent />
        </SceneErrorBoundary>
      </div>
    )

    // The rest of the app remains completely intact
    expect(screen.getByTestId('app-shell-header')).toBeInTheDocument()

    // Local error boundary renders fallback
    expect(screen.getByTestId('scene-error-fallback')).toBeInTheDocument()
    expect(screen.getByText(/3D Scene Rendering Unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/WEBGL_UNSUPPORTED/i)).toBeInTheDocument()

    // Error handler callback was notified
    expect(handleError).toHaveBeenCalledTimes(1)

    consoleErrorSpy.mockRestore()
  })

  it('supports custom fallback node', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <SceneErrorBoundary fallback={<div data-testid="custom-fallback">Custom 2D Fallback</div>}>
        <BrokenWebGLComponent />
      </SceneErrorBoundary>
    )

    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument()
    consoleErrorSpy.mockRestore()
  })

  it('allows retrying after an error has been caught', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    let shouldThrow = true
    const FlakyComponent: React.FC = () => {
      if (shouldThrow) {
        throw new Error('Temporary failure')
      }
      return <div data-testid="recovered-scene">Scene Recovered</div>
    }

    render(
      <SceneErrorBoundary>
        <FlakyComponent />
      </SceneErrorBoundary>
    )

    expect(screen.getByTestId('scene-error-fallback')).toBeInTheDocument()

    // Fix the error condition and click retry
    shouldThrow = false
    fireEvent.click(screen.getByRole('button', { name: /Retry 3D Scene/i }))

    expect(screen.getByTestId('recovered-scene')).toBeInTheDocument()
    expect(screen.queryByTestId('scene-error-fallback')).not.toBeInTheDocument()

    consoleErrorSpy.mockRestore()
  })
})

describe('LunarScene component and coordinate orientation', () => {
  it('applies agreed scene orientation (scene.x = east, scene.y = up, scene.z = -north)', () => {
    // East: (1, 0, 0)
    const eastScene = enuToLocalScene({ east: 1, north: 0, up: 0 })
    expect(eastScene).toEqual({ x: 1, y: 0, z: -0 })

    // North: (0, 1, 0) -> scene.z = -1
    const northScene = enuToLocalScene({ east: 0, north: 1, up: 0 })
    expect(northScene).toEqual({ x: 0, y: 0, z: -1 })

    // Up: (0, 0, 1) -> scene.y = 1
    const upScene = enuToLocalScene({ east: 0, north: 0, up: 1 })
    expect(upScene).toEqual({ x: 0, y: 1, z: -0 })
  })

  it('renders loading overlay when isLoading is true', () => {
    render(<LunarScene isLoading={true} />)
    expect(screen.getByTestId('scene-loading-overlay')).toBeInTheDocument()
    expect(screen.getByText(/Loading lunar scene ephemeris/i)).toBeInTheDocument()
  })

  it('renders demonstration banner only when demonstrationMode is true', () => {
    const { rerender } = render(<LunarScene demonstrationMode={false} />)
    expect(screen.queryByTestId('demonstration-banner')).not.toBeInTheDocument()

    rerender(<LunarScene demonstrationMode={true} />)
    expect(screen.getByTestId('demonstration-banner')).toBeInTheDocument()
    expect(screen.getByText(/Demonstration Vectors Only — Not Measured Ephemeris/i)).toBeInTheDocument()
  })

  it('renders container with default null directions without throwing', () => {
    render(<LunarScene sunDirectionEnu={null} earthDirectionEnu={null} />)
    expect(screen.getByTestId('lunar-scene-container')).toBeInTheDocument()
    expect(screen.getByText(/Sun: Awaiting vector/i)).toBeInTheDocument()
    expect(screen.getByText(/Earth: Awaiting vector/i)).toBeInTheDocument()
  })

  it('displays HUD azimuth and elevation labels from observationPoint', () => {
    const mockPoint: ObservationPoint = {
      timestamp: '2026-11-14T12:00:00Z',
      sun: {
        azimuth_deg: 145.2,
        elevation_deg: 1.5,
        horizon_elevation_deg: 0.0,
        visible: true,
        direction_enu: azimuthElevationToEnu(145.2, 1.5),
      },
      earth: {
        azimuth_deg: 350.0,
        elevation_deg: -2.3,
        horizon_elevation_deg: 0.0,
        visible: false,
        direction_enu: azimuthElevationToEnu(350.0, -2.3),
      },
      is_golden_window: false,
    }

    render(
      <LunarScene
        observationPoint={mockPoint}
        dataStatus="cached"
      />
    )

    expect(screen.getByTestId('hud-sun-label')).toHaveTextContent(/Sun: Az 145.2° · El 1.5° \(Visible\)/)
    expect(screen.getByTestId('hud-earth-label')).toHaveTextContent(/Earth: Az 350.0° · El -2.3° \(Below horizon\)/)
    expect(screen.getByText(/2026-11-14T12:00:00Z/)).toBeInTheDocument()
    expect(screen.getByText(/cached/)).toBeInTheDocument()
  })

  it('verifies agreement between numerical elevation and marker position above/below horizon', () => {
    // Sun at +1.5 deg elevation (above geometric horizon)
    const sunAboveEnu = azimuthElevationToEnu(180, 1.5)
    const sunAboveScene = enuToLocalScene(sunAboveEnu)
    expect(sunAboveScene.y).toBeGreaterThan(0) // Above y=0 horizon plane

    // Earth at -2.3 deg elevation (below geometric horizon)
    const earthBelowEnu = azimuthElevationToEnu(0, -2.3)
    const earthBelowScene = enuToLocalScene(earthBelowEnu)
    expect(earthBelowScene.y).toBeLessThan(0) // Below y=0 horizon plane

    // Exact horizontal vector (0.0 deg elevation)
    const horizonEnu = azimuthElevationToEnu(90, 0.0)
    const horizonScene = enuToLocalScene(horizonEnu)
    expect(horizonScene.y).toBeCloseTo(0, 6) // Exactly on the horizon plane
  })

  it('updates scene HUD and vectors when observation timestamp changes', () => {
    const point1: ObservationPoint = {
      timestamp: '2026-11-14T12:00:00Z',
      sun: {
        azimuth_deg: 100.0,
        elevation_deg: 5.0,
        horizon_elevation_deg: 0.0,
        visible: true,
        direction_enu: azimuthElevationToEnu(100.0, 5.0),
      },
      earth: {
        azimuth_deg: 200.0,
        elevation_deg: 10.0,
        horizon_elevation_deg: 0.0,
        visible: true,
        direction_enu: azimuthElevationToEnu(200.0, 10.0),
      },
      is_golden_window: true,
    }

    const { rerender } = render(<LunarScene observationPoint={point1} />)
    expect(screen.getByText('2026-11-14T12:00:00Z')).toBeInTheDocument()
    expect(screen.getByTestId('hud-sun-label')).toHaveTextContent(/El 5.0°/)

    // Update to new observation instant
    const point2: ObservationPoint = {
      ...point1,
      timestamp: '2026-11-14T13:00:00Z',
      sun: {
        ...point1.sun,
        azimuth_deg: 105.0,
        elevation_deg: 4.5,
        direction_enu: azimuthElevationToEnu(105.0, 4.5),
      },
    }

    rerender(<LunarScene observationPoint={point2} />)
    expect(screen.getByText('2026-11-14T13:00:00Z')).toBeInTheDocument()
    expect(screen.getByTestId('hud-sun-label')).toHaveTextContent(/El 4.5°/)
  })

  it('displays geometric horizon reference notice indicating no terrain occlusion in Stage 1', () => {
    render(<LunarScene />)
    const notice = screen.getByTestId('scene-horizon-notice')
    expect(notice).toHaveTextContent(/Geometric Reference Horizon \(Elevation 0.0°\)/)
    expect(notice).toHaveTextContent(/Terrain occlusion not modeled in Stage 1/)
  })
})
