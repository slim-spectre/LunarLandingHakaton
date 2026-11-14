import React from 'react'
import type { SceneSlotProps } from './types'

/**
 * Reserved 3D local terrain scene area.
 * Owned by Slavik.
 *
 * Integrates Three.js / React Three Fiber and topocentric ENU vectors.
 */
export const SceneSlot: React.FC<SceneSlotProps> = ({
  className = '',
  regionId,
  sunDirectionEnu,
  earthDirectionEnu,
  observerHeightM = 2,
}) => {
  return (
    <section className={`slot-container scene-slot ${className}`} data-testid="scene-slot">
      <div className="slot-header">
        <h3 className="slot-title">3D Local Terrain Scene</h3>
        <span className="slot-badge reserved-badge">Reserved (Slavik)</span>
      </div>
      <div className="slot-body placeholder-body">
        <div className="slot-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
        </div>
        <p className="slot-heading">Three.js / React Three Fiber Viewport</p>
        <p className="slot-description">
          Local elevation heightmap mesh with topocentric ENU vectors for Sun and Earth directions.
        </p>
        <div className="slot-metadata">
          <span>Observer Height: {observerHeightM}m</span>
          {regionId && <span>Region: {regionId}</span>}
          {sunDirectionEnu && (
            <span>
              Sun ENU: [{sunDirectionEnu.east.toFixed(3)}, {sunDirectionEnu.north.toFixed(3)}, {sunDirectionEnu.up.toFixed(3)}]
            </span>
          )}
          {earthDirectionEnu && (
            <span>
              Earth ENU: [{earthDirectionEnu.east.toFixed(3)}, {earthDirectionEnu.north.toFixed(3)}, {earthDirectionEnu.up.toFixed(3)}]
            </span>
          )}
          {!sunDirectionEnu && !earthDirectionEnu && (
            <span>Status: Awaiting ephemeris calculation vectors</span>
          )}
        </div>
      </div>
    </section>
  )
}
