import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import { SceneErrorBoundary } from './SceneErrorBoundary'
import { LunarScene } from './LunarScene'

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
    // Suppress console.error in test output for intentional error boundary test
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

describe('LunarScene component', () => {
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
  })
})
