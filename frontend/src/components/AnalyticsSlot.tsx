import React from 'react'
import type { AnalyticsSlotProps } from './types'

/**
 * Reserved area for timeline, solar elevation, and communication analytics.
 *
 * Rules:
 * - Must not display fabricated golden windows or operational values.
 * - Must not calculate astronomical or ephemeris values in React components.
 */
export const AnalyticsSlot: React.FC<AnalyticsSlotProps> = ({ className = '' }) => {
  return (
    <section className={`slot-container analytics-slot ${className}`} data-testid="analytics-slot">
      <div className="slot-header">
        <h3 className="slot-title">Mission Timeline & Visibility Analytics</h3>
        <span className="slot-badge planned-badge">Stage 1 Planned</span>
      </div>
      <div className="slot-body placeholder-body">
        <div className="slot-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="18" y1="20" x2="18" y2="10" />
            <line x1="12" y1="20" x2="12" y2="4" />
            <line x1="6" y1="20" x2="6" y2="14" />
            <line x1="2" y1="20" x2="22" y2="20" />
          </svg>
        </div>
        <p className="slot-heading">Timeline & Analysis Panel</p>
        <p className="slot-description">
          Awaiting real calculation results from Stage 1 backend endpoints. No simulated or fabricated operational values are displayed prior to real data arrival.
        </p>
        <div className="slot-metadata">
          <span>Golden Windows: None (Awaiting Calculation)</span>
          <span>Sun Visibility: Uncomputed</span>
          <span>Earth Visibility: Uncomputed</span>
        </div>
      </div>
    </section>
  )
}
