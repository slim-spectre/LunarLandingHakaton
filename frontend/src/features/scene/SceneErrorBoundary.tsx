import { Component, type ErrorInfo, type ReactNode } from 'react'

export interface SceneErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface SceneErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/**
 * Local error boundary isolating 3D Scene and WebGL failures.
 *
 * Prevents WebGL context creation errors or Three.js runtime crashes
 * from breaking the surrounding application shell.
 */
export class SceneErrorBoundary extends Component<SceneErrorBoundaryProps, SceneErrorBoundaryState> {
  public override state: SceneErrorBoundaryState = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): SceneErrorBoundaryState {
    return { hasError: true, error }
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  public override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div
          role="alert"
          className="scene-error-fallback"
          data-testid="scene-error-fallback"
          style={{
            padding: '1.5rem',
            backgroundColor: 'rgba(255, 77, 79, 0.1)',
            border: '1px solid #ff4d4f',
            borderRadius: '6px',
            color: '#fff',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            minHeight: '260px',
            textAlign: 'center',
            gap: '0.75rem',
          }}
        >
          <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#ff7875' }}>
            3D Scene Rendering Unavailable
          </div>
          <p style={{ margin: 0, fontSize: '0.875rem', color: '#d9d9d9', maxWidth: '420px' }}>
            {this.state.error?.message ||
              'A WebGL or rendering error occurred. The remainder of the application remains fully functional.'}
          </p>
          <button
            type="button"
            onClick={this.handleRetry}
            style={{
              marginTop: '0.5rem',
              padding: '0.4rem 1rem',
              backgroundColor: '#1f1f1f',
              border: '1px solid #434343',
              borderRadius: '4px',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.85rem',
            }}
          >
            Retry 3D Scene
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
