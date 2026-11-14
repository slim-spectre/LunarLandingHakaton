/**
 * Types for 3D Lunar Local Scene Visualization (Stage 1)
 */

import type { EnuVector } from '../../lib/coordinates'
import type { NowResult, ResolvedSite, Site } from '../../api/types'

export type ObservationPoint = NowResult['point']

export interface LunarSceneProps {
  className?: string
  /**
   * Topocentric ENU unit direction vector towards the Sun.
   * Null when not yet calculated or unavailable.
   */
  sunDirectionEnu?: EnuVector | null
  /**
   * Topocentric ENU unit direction vector towards Earth.
   * Null when not yet calculated or unavailable.
   */
  earthDirectionEnu?: EnuVector | null
  /**
   * Direct observation point matching canonical API contract.
   * If provided, timestamp and azimuth/elevation angles are extracted directly.
   */
  observationPoint?: ObservationPoint | null
  /**
   * Resolved or catalog site.
   */
  site?: ResolvedSite | Site | null
  /**
   * Height of the observer above the model surface in metres.
   * Default: 2.0 metres.
   */
  observerHeightM?: number
  /**
   * Whether ephemeris or terrain data is currently loading.
   */
  isLoading?: boolean
  /**
   * Data status from result metadata ('fresh' | 'cached').
   */
  dataStatus?: 'fresh' | 'cached' | null
  /**
   * Explicit requested observation timestamp (preserved across cached requests).
   */
  timestamp?: string | null
  /**
   * Reserved for Stage 2 physical terrain elevation heightmap.
   */
  heightmap?: unknown | null
  /**
   * Multiplier used strictly for rendering distance/marker visibility.
   * Kept strictly separated from physical coordinates.
   * Default: 1.0.
   */
  visualScale?: number
  /**
   * Optional flag indicating that demonstration vectors are active.
   * When true, an explicit demonstration badge is shown.
   */
  demonstrationMode?: boolean
  /**
   * Optional callback triggered if a WebGL rendering error occurs.
   */
  onError?: (error: Error) => void
}
