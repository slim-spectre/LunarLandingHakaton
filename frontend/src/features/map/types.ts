import type { LunarCoordinate } from '../../lib/coordinates'

export type { LunarCoordinate }

export interface LunarMapProps {
  className?: string
  /**
   * Currently selected lunar coordinate (latitude [-90, 90], longitude [-180, 180)).
   */
  selectedCoordinate?: LunarCoordinate | null
  /**
   * Callback invoked when a user selects a coordinate on the map.
   */
  onSelectCoordinate?: (coord: LunarCoordinate) => void
  /**
   * Optional identifier of selected catalog site.
   */
  selectedSiteId?: string | null
  /**
   * Whether map tiles or catalog data is currently loading.
   */
  isLoading?: boolean
  /**
   * Whether map or projection layer is unavailable.
   */
  isUnavailable?: boolean
  /**
   * Human-readable explanation if map is unavailable.
   */
  unavailableReason?: string
}
