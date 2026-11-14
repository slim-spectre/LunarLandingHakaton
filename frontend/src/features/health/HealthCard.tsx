import React from 'react'
import { useHealth } from './useHealth'
import { resolveApiBaseUrl } from '../../api/client'

export const HealthCard: React.FC = () => {
  const { status, health, error, isDemoMode, refresh } = useHealth()
  const apiUrl = resolveApiBaseUrl()

  return (
    <section className="slot-container health-card" data-testid="health-card">
      <div className="slot-header">
        <h3 className="slot-title">System & Backend Health</h3>
        <div className="status-badge-group">
          {isDemoMode && (
            <span className="demo-badge" data-testid="demo-badge">
              DEMO / TEST DATA
            </span>
          )}
          <span className={`status-badge status-${status}`} data-testid="status-badge">
            {status === 'loading' && 'Checking...'}
            {status === 'healthy' && 'Healthy'}
            {status === 'database_unavailable' && 'DB Unavailable'}
            {status === 'network_unreachable' && 'Network Unreachable'}
            {status === 'error' && 'API Error'}
          </span>
        </div>
      </div>

      <div className="slot-body">
        <div className="health-details">
          <div className="detail-row">
            <span className="detail-label">API Endpoint:</span>
            <span className="detail-value mono" data-testid="api-url">
              {apiUrl}
            </span>
          </div>

          {status === 'loading' && (
            <div className="state-message state-loading" data-testid="state-loading">
              <span className="spinner" aria-hidden="true" />
              <span>Verifying backend service and database connectivity...</span>
            </div>
          )}

          {status === 'healthy' && health && (
            <div className="state-message state-healthy" data-testid="state-healthy">
              <div className="detail-row">
                <span className="detail-label">Service:</span>
                <span className="detail-value mono">{health.service}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Database:</span>
                <span className="detail-value mono status-ok">{health.database}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Reported Time:</span>
                <span className="detail-value mono">{health.timestamp}</span>
              </div>
            </div>
          )}

          {status === 'database_unavailable' && (
            <div className="state-message state-error" data-testid="state-database-unavailable">
              <div className="error-title">Database Unavailable (HTTP 503)</div>
              <div className="error-description">
                {error?.message || 'PostgreSQL database connectivity check failed.'}
              </div>
              {error?.code && (
                <div className="detail-row">
                  <span className="detail-label">Code:</span>
                  <span className="detail-value mono error-code">{error.code}</span>
                </div>
              )}
              {error?.requestId && (
                <div className="detail-row">
                  <span className="detail-label">Request ID:</span>
                  <span className="detail-value mono">{error.requestId}</span>
                </div>
              )}
            </div>
          )}

          {status === 'network_unreachable' && (
            <div className="state-message state-error" data-testid="state-network-unreachable">
              <div className="error-title">Network Unreachable</div>
              <div className="error-description">
                Unable to reach the backend service at <code className="mono">{apiUrl}</code>. Ensure the backend server is running on the expected host/port.
              </div>
              {error?.code && (
                <div className="detail-row">
                  <span className="detail-label">Error Code:</span>
                  <span className="detail-value mono error-code">{error.code}</span>
                </div>
              )}
            </div>
          )}

          {status === 'error' && (
            <div className="state-message state-error" data-testid="state-api-error">
              <div className="error-title">API Request Failed</div>
              <div className="error-description">{error?.message}</div>
              {error?.code && (
                <div className="detail-row">
                  <span className="detail-label">Code:</span>
                  <span className="detail-value mono error-code">{error.code}</span>
                </div>
              )}
              {error?.requestId && (
                <div className="detail-row">
                  <span className="detail-label">Request ID:</span>
                  <span className="detail-value mono">{error.requestId}</span>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="health-actions">
          <button
            type="button"
            className="refresh-button"
            onClick={() => refresh()}
            disabled={status === 'loading'}
            data-testid="refresh-button"
          >
            {status === 'loading' ? 'Checking...' : 'Refresh Health'}
          </button>
        </div>
      </div>
    </section>
  )
}
