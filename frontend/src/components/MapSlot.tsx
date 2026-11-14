import React from 'react'
import type { MapSlotProps } from './types'

/**
 * Reserved map area for lunar surface and projections.
 * Owned by Slavik.
 */
export const MapSlot: React.FC<MapSlotProps> = ({
  className = '',
  selectedSiteId,
  targetCoordinates,
}) => {
  return (
    <section className={`slot-container map-slot ${className}`} data-testid="map-slot">
      <div className="slot-header">
        <h3 className="slot-title">Lunar Surface Map</h3>
        <span className="slot-badge reserved-badge">Reserved (Slavik)</span>
      </div>
      <div className="slot-body placeholder-body">
        <div className="slot-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 3a9 9 0 0 0 0 18M3 12h18" strokeDasharray="2 2" />
            <circle cx="9" cy="9" r="1.5" />
            <circle cx="15" cy="14" r="1" />
            <circle cx="13" cy="7" r="0.75" />
          </svg>
        </div>
        <p className="slot-heading">Map & Projection Viewport</p>
        <p className="slot-description">
          OpenLayers integration slot supporting custom lunar WMS/WMTS projections (Moon Trek / LROC).
        </p>
        <div className="slot-metadata">
          {selectedSiteId && <span>Selected Site: {selectedSiteId}</span>}
          {targetCoordinates && (
            <span>
              Target: {targetCoordinates.latitude.toFixed(4)}°, {targetCoordinates.longitude.toFixed(4)}°
            </span>
          )}
          {!selectedSiteId && !targetCoordinates && (
            <span>Status: Awaiting coordinate selection</span>
          )}
        </div>
      </div>
    </section>
  )
}
