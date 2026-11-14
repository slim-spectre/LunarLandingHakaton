/**
 * Shared component slot contracts and coordinate conventions.
 *
 * Owned coordination interface with Slavik for map, scene, and analytics integrations.
 */

/**
 * Agreed East-North-Up (ENU) topocentric unit direction or displacement vector.
 *
 * Rules:
 * - Directions are unit vectors without a display distance multiplier.
 * - East = +X, North = +Y, Up = +Z in local topocentric tangent plane.
 */
export interface EnuVector {
  east: number
  north: number
  up: number
}

/**
 * Props for the MapSlot component (owned by Slavik).
 */
export interface MapSlotProps {
  className?: string
  selectedSiteId?: string | null
  targetCoordinates?: {
    latitude: number
    longitude: number
  } | null
  onCoordinateSelect?: (coords: { latitude: number; longitude: number }) => void
}

/**
 * Props for the SceneSlot component (owned by Slavik).
 */
export interface SceneSlotProps {
  className?: string
  regionId?: string | null
  sunDirectionEnu?: EnuVector | null
  earthDirectionEnu?: EnuVector | null
  observerHeightM?: number
}

/**
 * Props for the AnalyticsSlot component.
 */
export interface AnalyticsSlotProps {
  className?: string
}
