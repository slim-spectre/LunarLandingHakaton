import React, { useRef, useCallback } from 'react'
import { normalizeLongitude } from '../../lib/coordinates'
import type { LunarMapProps } from './types'

/**
 * Minimal Reusable Lunar Map Component for Stage 0.
 *
 * Supports:
 * - Selected lunar coordinate visualization and marker
 * - Interactive coordinate selection callback
 * - Loading and unavailable states
 * - Designed for OpenLayers integration with Moon Trek / LROC WMS/WMTS layers in Stage 1
 *
 * No mock provider URLs or unauthorized tile matrix sets are hardcoded.
 */
export const LunarMap: React.FC<LunarMapProps> = ({
  className = '',
  selectedCoordinate,
  onSelectCoordinate,
  selectedSiteId,
  isLoading = false,
  isUnavailable = false,
  unavailableReason,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null)

  /**
   * Handle coordinate selection from click on the lunar projection viewport.
   * Maps relative click coordinates (x: 0..1, y: 0..1) to lunar latitude [-90, 90] and longitude [-180, 180).
   */
  const handleViewportClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      if (!onSelectCoordinate || isUnavailable || isLoading) return

      const rect = event.currentTarget.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return

      const clickX = (event.clientX - rect.left) / rect.width
      const clickY = (event.clientY - rect.top) / rect.height

      // Map Y from [0, 1] (top-to-bottom) to latitude [90, -90] (North to South)
      const rawLat = 90.0 - clickY * 180.0
      const clampedLat = Math.max(-90.0, Math.min(90.0, rawLat))

      // Map X from [0, 1] (left-to-right) to longitude [-180, 180)
      const rawLon = -180.0 + clickX * 360.0
      const normLon = normalizeLongitude(rawLon)

      onSelectCoordinate({
        latitude: Math.round(clampedLat * 1e4) / 1e4,
        longitude: normLon,
      })
    },
    [onSelectCoordinate, isUnavailable, isLoading]
  )

  /**
   * Calculate pixel percentage positions for the selected coordinate marker.
   */
  const markerPosition = selectedCoordinate
    ? {
        left: `${((normalizeLongitude(selectedCoordinate.longitude) + 180.0) / 360.0) * 100}%`,
        top: `${((90.0 - Math.max(-90, Math.min(90, selectedCoordinate.latitude))) / 180.0) * 100}%`,
      }
    : null

  return (
    <div
      ref={mapContainerRef}
      className={`lunar-map-container ${className}`}
      data-testid="lunar-map-container"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '280px',
        backgroundColor: '#0c0d12',
        border: '1px solid #262626',
        borderRadius: '6px',
        overflow: 'hidden',
        userSelect: 'none',
      }}
    >
      {/* Map Header / Status Bar */}
      <div
        className="lunar-map-status-bar"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          padding: '6px 12px',
          backgroundColor: 'rgba(12, 13, 18, 0.85)',
          borderBottom: '1px solid #1f1f1f',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.75rem',
          color: '#8c8c8c',
          zIndex: 10,
        }}
      >
        <span>
          {selectedSiteId
            ? `Site: ${selectedSiteId}`
            : selectedCoordinate
              ? `Coord: ${selectedCoordinate.latitude.toFixed(4)}°, ${normalizeLongitude(selectedCoordinate.longitude).toFixed(4)}°`
              : 'Awaiting coordinate selection'}
        </span>
        <span style={{ fontSize: '0.7rem' }}>Click viewport to pick coordinates</span>
      </div>

      {/* Interactive Lunar Map Projection Viewport */}
      <div
        data-testid="lunar-map-viewport"
        onClick={handleViewportClick}
        style={{
          position: 'absolute',
          top: '32px',
          left: 0,
          right: 0,
          bottom: 0,
          cursor: onSelectCoordinate && !isUnavailable && !isLoading ? 'crosshair' : 'default',
          backgroundImage:
            'radial-gradient(circle at center, rgba(38, 38, 38, 0.4) 0%, rgba(12, 13, 18, 0.95) 100%)',
        }}
      >
        {/* Equirectangular Grid Lines (15-degree indicators) */}
        <svg
          width="100%"
          height="100%"
          style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
          aria-hidden="true"
        >
          {/* Equator */}
          <line x1="0" y1="50%" x2="100%" y2="50%" stroke="rgba(255, 255, 255, 0.15)" strokeDasharray="4 4" />
          {/* Prime Meridian */}
          <line x1="50%" y1="0" x2="50%" y2="100%" stroke="rgba(255, 255, 255, 0.15)" strokeDasharray="4 4" />
          {/* South Polar Boundary line (-80 deg latitude ~ 94.4% Y) */}
          <line x1="0" y1="94.4%" x2="100%" y2="94.4%" stroke="rgba(24, 144, 255, 0.25)" strokeDasharray="2 2" />
        </svg>

        {/* Selected Coordinate Marker */}
        {markerPosition && (
          <div
            data-testid="lunar-coordinate-marker"
            style={{
              position: 'absolute',
              left: markerPosition.left,
              top: markerPosition.top,
              transform: 'translate(-50%, -50%)',
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              backgroundColor: '#52c41a',
              border: '2px solid #ffffff',
              boxShadow: '0 0 8px rgba(82, 196, 26, 0.8)',
              pointerEvents: 'none',
              zIndex: 5,
            }}
          />
        )}
      </div>

      {/* Loading Overlay */}
      {isLoading && (
        <div
          data-testid="lunar-map-loading"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(12, 13, 18, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#d9d9d9',
            fontSize: '0.85rem',
            zIndex: 20,
          }}
        >
          Loading lunar map layer...
        </div>
      )}

      {/* Unavailable State */}
      {isUnavailable && (
        <div
          data-testid="lunar-map-unavailable"
          role="status"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(12, 13, 18, 0.9)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem',
            textAlign: 'center',
            color: '#8c8c8c',
            zIndex: 25,
            gap: '0.5rem',
          }}
        >
          <span style={{ color: '#ff4d4f', fontWeight: 600 }}>Lunar Map Unavailable</span>
          <span style={{ fontSize: '0.8rem', maxWidth: '360px' }}>
            {unavailableReason || 'Layer data or projection is currently unavailable for the requested region.'}
          </span>
        </div>
      )}
    </div>
  )
}
