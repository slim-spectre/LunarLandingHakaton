import React, { useRef, useCallback, useState, useMemo } from 'react'
import { normalizeLongitude } from '../../lib/coordinates'
import { resolveApiBaseUrl } from '../../api/client'
import {
  VERIFIED_MAP_LAYERS,
  isCoordinateInLayerExtent,
  buildLayerImageUrl,
} from './layers'
import type { LunarMapProps } from './types'

/**
 * Lunar Map Component implementing Stage 1 map foundations:
 * - Real verified map layers (Moon Trek WMTS and LROC WMS)
 * - Map layer switching respecting lunar CRS and parameters
 * - Provider attribution and official source links
 * - Verified QuickMap links from catalog data
 * - Selected site marker and click coordinate selection
 * - Coverage boundary checks and provider error handling
 * - Clean fallback without misrepresenting missing imagery as terrain
 */
export const LunarMap: React.FC<LunarMapProps> = ({
  className = '',
  selectedCoordinate,
  onSelectCoordinate,
  selectedSiteId,
  quickmapUrl,
  activeLayerId: controlledLayerId,
  onLayerChange,
  layers = VERIFIED_MAP_LAYERS,
  isLoading = false,
  isUnavailable = false,
  unavailableReason,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const [internalLayerId, setInternalLayerId] = useState<string>(
    layers[0]?.id ?? 'LRO_WAC_Mosaic_Global_303ppd_v02'
  )
  const [layerImageError, setLayerImageError] = useState<boolean>(false)

  const activeLayerId = controlledLayerId ?? internalLayerId
  const activeLayer = useMemo(() => {
    return layers.find((l) => l.id === activeLayerId) ?? layers[0] ?? VERIFIED_MAP_LAYERS[0]
  }, [layers, activeLayerId])

  const handleLayerSelect = (newId: string) => {
    setInternalLayerId(newId)
    setLayerImageError(false)
    if (onLayerChange) {
      onLayerChange(newId)
    }
  }

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

  // Check if selected coordinate is outside active layer's coverage extent
  const isOutsideCoverage = useMemo(() => {
    if (!selectedCoordinate || !activeLayer) return false
    return !isCoordinateInLayerExtent(selectedCoordinate, activeLayer)
  }, [selectedCoordinate, activeLayer])

  // Build proxy URL for backend layer image
  const layerImageUrl = useMemo(() => {
    if (!activeLayer) return null
    return buildLayerImageUrl(activeLayer, resolveApiBaseUrl())
  }, [activeLayer])

  return (
    <div
      ref={mapContainerRef}
      className={`lunar-map-container ${className}`}
      data-testid="lunar-map-container"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '340px',
        backgroundColor: '#0c0d12',
        border: '1px solid #262626',
        borderRadius: '6px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        userSelect: 'none',
      }}
    >
      {/* Top Controls: Layer Switcher & Coordinate Status */}
      <div
        className="lunar-map-controls-bar"
        style={{
          padding: '6px 10px',
          backgroundColor: 'rgba(18, 19, 26, 0.95)',
          borderBottom: '1px solid #262626',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '6px',
          fontSize: '0.75rem',
          color: '#a0a0a0',
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label htmlFor="map-layer-select" style={{ fontWeight: 600, color: '#d9d9d9' }}>
            Layer:
          </label>
          <select
            id="map-layer-select"
            data-testid="map-layer-select"
            value={activeLayer.id}
            onChange={(e) => handleLayerSelect(e.target.value)}
            style={{
              padding: '2px 6px',
              backgroundColor: '#1f1f24',
              border: '1px solid #333',
              borderRadius: '4px',
              color: '#fff',
              fontSize: '0.75rem',
              maxWidth: '220px',
            }}
          >
            {layers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.provider === 'moon_trek' ? 'Moon Trek WMTS' : 'LROC WMS'})
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {selectedSiteId && (
            <span style={{ color: '#52c41a', fontWeight: 600 }}>Site: {selectedSiteId}</span>
          )}
          {selectedCoordinate && (
            <span>
              {selectedCoordinate.latitude.toFixed(4)}°, {normalizeLongitude(selectedCoordinate.longitude).toFixed(4)}°
            </span>
          )}
          {!selectedCoordinate && !selectedSiteId && (
            <span style={{ color: '#777' }}>Awaiting selection</span>
          )}
        </div>
      </div>

      {/* Interactive Lunar Map Projection Viewport */}
      <div
        data-testid="lunar-map-viewport"
        onClick={handleViewportClick}
        style={{
          position: 'relative',
          flex: 1,
          width: '100%',
          minHeight: '190px',
          cursor: onSelectCoordinate && !isUnavailable && !isLoading ? 'crosshair' : 'default',
          backgroundColor: '#050508',
          overflow: 'hidden',
        }}
      >
        {/* Layer Image Preview */}
        {layerImageUrl && !layerImageError && !isUnavailable && (
          <img
            src={layerImageUrl}
            alt={activeLayer.name}
            data-testid="lunar-layer-image"
            onError={() => setLayerImageError(true)}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              opacity: 0.85,
            }}
          />
        )}

        {/* Fallback Graphic & Equirectangular Grid Lines */}
        <svg
          width="100%"
          height="100%"
          style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
          aria-hidden="true"
        >
          {/* Equator */}
          <line x1="0" y1="50%" x2="100%" y2="50%" stroke="rgba(255, 255, 255, 0.2)" strokeDasharray="4 4" />
          {/* Prime Meridian */}
          <line x1="50%" y1="0" x2="50%" y2="100%" stroke="rgba(255, 255, 255, 0.2)" strokeDasharray="4 4" />
          {/* South Polar Boundary line (-80 deg latitude ~ 94.4% Y) */}
          <line x1="0" y1="94.4%" x2="100%" y2="94.4%" stroke="rgba(24, 144, 255, 0.35)" strokeDasharray="2 2" />
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
              boxShadow: '0 0 10px rgba(82, 196, 26, 0.9)',
              pointerEvents: 'none',
              zIndex: 5,
            }}
          />
        )}

        {/* Coverage Warning Banner */}
        {isOutsideCoverage && (
          <div
            data-testid="layer-outside-coverage-banner"
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              padding: '4px 8px',
              backgroundColor: 'rgba(250, 173, 20, 0.25)',
              border: '1px solid #faad14',
              borderRadius: '4px',
              color: '#faad14',
              fontSize: '0.75rem',
              fontWeight: 600,
              zIndex: 6,
            }}
          >
            Location outside layer coverage
          </div>
        )}

        {/* Layer Image Error Notification */}
        {layerImageError && !isUnavailable && (
          <div
            data-testid="layer-image-error-notice"
            style={{
              position: 'absolute',
              bottom: '8px',
              left: '8px',
              padding: '4px 8px',
              backgroundColor: 'rgba(255, 77, 79, 0.2)',
              border: '1px solid #ff4d4f',
              borderRadius: '4px',
              color: '#ff7875',
              fontSize: '0.7rem',
              zIndex: 6,
            }}
          >
            Layer imagery unavailable from provider (using schematic projection)
          </div>
        )}
      </div>

      {/* Layer Metadata, Projection CRS & Attribution Bar */}
      <div
        className="lunar-map-attribution-bar"
        data-testid="lunar-map-attribution-bar"
        style={{
          padding: '6px 10px',
          backgroundColor: '#0f1016',
          borderTop: '1px solid #1f2029',
          fontSize: '0.7rem',
          color: '#858595',
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '4px' }}>
          <div>
            <span style={{ fontWeight: 600, color: '#bbb' }}>CRS:</span>{' '}
            <code style={{ color: '#4096ff' }}>{activeLayer.crs_id}</code> ({activeLayer.coordinate_units})
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {activeLayer.source_url && (
              <a
                href={activeLayer.source_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#1890ff', textDecoration: 'none' }}
              >
                Capabilities ↗
              </a>
            )}
            {quickmapUrl && (
              <a
                href={quickmapUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="quickmap-link"
                style={{ color: '#52c41a', textDecoration: 'none', fontWeight: 600 }}
              >
                View in QuickMap ↗
              </a>
            )}
          </div>
        </div>
        <div style={{ color: '#707080', fontSize: '0.65rem' }}>
          {activeLayer.attribution}
        </div>
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
          Loading lunar map layer…
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
            backgroundColor: 'rgba(12, 13, 18, 0.92)',
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
