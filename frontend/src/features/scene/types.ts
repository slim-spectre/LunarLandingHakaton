/**
 * Types for 3D Lunar Local Scene Visualization
 */

import type { EnuVector } from '../../lib/coordinates'

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
   * Height of the observer above the model surface in metres.
   * Default: 2.0 metres.
   */
  observerHeightM?: number
  /**
   * Whether ephemeris or terrain data is currently loading.
   */
  isLoading?: boolean
  /**
   * Multiplier used strictly for rendering distance/marker visibility.
   * Kept strictly separated from physical coordinates.
   * Default: 10.0 (scene units).
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
