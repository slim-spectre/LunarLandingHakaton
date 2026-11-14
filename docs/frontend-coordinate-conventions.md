# Frontend Coordinate Conventions and Map/Scene Integration

Documented conventions, coordinate frames, axis signs, units, component props, and integration instructions for the map and 3D local scene in **Stage 0**.

---

## 1. Coordinate Frames

### 1.1 Moon-Centered Moon-Fixed (MCMF) Global Frame
The lunar body-fixed Cartesian system represents directions and positions relative to the Moon's center:
- **+X axis**: Passes through the lunar equator and prime meridian (0° Latitude, 0° Longitude).
- **+Y axis**: Passes through the lunar equator at 90° East (0° Latitude, +90° Longitude).
- **+Z axis**: Aligns with the lunar rotation axis pointing toward the North Pole (+90° Latitude).

Conversion from lunar latitude $\phi \in [-90, 90]$ and normalized longitude $\lambda \in [-180, 180)$ to unit Cartesian coordinates $[x, y, z]$:
$$x = \cos(\phi) \cdot \cos(\lambda)$$
$$y = \cos(\phi) \cdot \sin(\lambda)$$
$$z = \sin(\phi)$$

*Note: The Moon is represented as a unit sphere for directional geometry. Physical lunar radii, vertical datums, and terrain elevation models are applied as separate vertical offsets. Earth dimensions, WGS84, or Earth geoids are never used.*

### 1.2 Topocentric East-North-Up (ENU) Local Frame
The local tangent coordinate system at an observer's location on the lunar surface:
- **East (+X)**: Tangent to the local parallel pointing east (direction of increasing longitude).
- **North (+Y)**: Tangent to the local meridian pointing north (direction of increasing latitude).
- **Up (+Z)**: Local geometric vertical pointing away from the Moon's center toward the local zenith.

Units: Dimensionless unit vectors for directions ($\sqrt{E^2 + N^2 + U^2} = 1$).

### 1.3 Local Three.js Scene Frame
Three.js uses a right-handed Cartesian coordinate system where the default camera looks down the negative Z axis. To align local topocentric geometry naturally with camera navigation, the agreed mapping from ENU is:
$$\text{scene.x} = +\text{east}$$
$$\text{scene.y} = +\text{up}$$
$$\text{scene.z} = -\text{north}$$

| ENU Vector | Direction | Three.js Scene Coordinate |
| :--- | :--- | :--- |
| $[1, 0, 0]$ | East | $[1, 0, 0]$ |
| $[0, 1, 0]$ | North | $[0, 0, -1]$ |
| $[0, 0, 1]$ | Up / Zenith | $[0, 1, 0]$ |
| $[-1, 0, 0]$ | West | $[-1, 0, 0]$ |
| $[0, -1, 0]$ | South | $[0, 0, 1]$ |
| $[0, 0, -1]$ | Down / Nadir | $[0, -1, 0]$ |

Visual scaling (such as marker distance multipliers or observer height exaggeration) is maintained strictly separate from underlying physical coordinates.

---

## 2. Units and Angular Conventions

- **Latitude**: Decimal degrees in $[-90.0, 90.0]$.
- **Longitude**: Input accepted in $[-180.0, 360.0)$; normalized to $[-180.0, 180.0)$ using:
  $$\text{normalized} = ((\text{longitude} + 180) \bmod 360) - 180$$
- **Azimuth**: Decimal degrees in $[0.0, 360.0)$, measured clockwise from North ($0^\circ = \text{North}$, $90^\circ = \text{East}$, $180^\circ = \text{South}$, $270^\circ = \text{West}$).
- **Elevation**: Decimal degrees in $[-90.0, 90.0]$ relative to the local horizontal tangent plane ($0^\circ = \text{horizon}$, $+90^\circ = \text{zenith}$, $-90^\circ = \text{nadir}$).
  - Zero elevation produces a strictly horizontal vector ($\text{up} = 0$).
  - Positive elevation points upward ($\text{up} > 0$).
- **Observer Height**: Metres above base model surface (default: $2.0\,\text{m}$, allowed range: $0$--$20\,\text{m}$).

---

## 3. Component Interfaces and Props

### 3.1 `LunarMap` (`frontend/src/features/map/`)
Reusable 2D lunar map component ready for OpenLayers integration in Stage 1.

```typescript
export interface LunarMapProps {
  className?: string
  /** Selected lunar coordinate (latitude [-90, 90], longitude [-180, 180)) */
  selectedCoordinate?: LunarCoordinate | null
  /** Callback triggered when user clicks or selects a point on the map */
  onSelectCoordinate?: (coord: LunarCoordinate) => void
  /** Optional ID of selected catalog landing site */
  selectedSiteId?: string | null
  /** Loading state flag */
  isLoading?: boolean
  /** Unavailable state flag (e.g. when DEM or layer coverage is absent) */
  isUnavailable?: boolean
  /** Reason for unavailability displayed to user */
  unavailableReason?: string
}
```

### 3.2 `LunarScene` (`frontend/src/features/scene/`)
Reusable 3D local scene component rendered via Three.js / React Three Fiber.

```typescript
export interface LunarSceneProps {
  className?: string
  /** Topocentric ENU unit direction toward Sun (null if uncalculated or unavailable) */
  sunDirectionEnu?: EnuVector | null
  /** Topocentric ENU unit direction toward Earth (null if uncalculated or unavailable) */
  earthDirectionEnu?: EnuVector | null
  /** Observer height in metres above surface (default: 2.0) */
  observerHeightM?: number
  /** Loading state flag */
  isLoading?: boolean
  /** Visual scale multiplier for rendering distance (separated from physical coords) */
  visualScale?: number
  /** When true, displays explicit 'Demonstration Vectors Only' banner */
  demonstrationMode?: boolean
  /** Callback on WebGL / rendering error */
  onError?: (error: Error) => void
}
```

### 3.3 `SceneErrorBoundary` (`frontend/src/features/scene/`)
React Error Boundary dedicated to isolating WebGL failures (unsupported context, shader compilation error, GPU crash).
- Prevents scene crashes from breaking the surrounding application shell.
- Displays a clean, localized error message with a "Retry 3D Scene" action.
- Allows passing a custom `fallback` element.

---

## 4. Stage 1 Moon Trek / LROC Connection Blueprint

In Stage 1, `LunarMap` will attach official OpenLayers tile and image sources via the API v1 catalog (`/api/v1/map/layers`):
1. **WMTS Layers** (e.g. LROC WAC Global Mosaic):
   - Attached using `ol/layer/Tile` with `ol/source/WMTS`.
   - Tile matrix identifiers (`tile_matrix_set`) and row/col indices fetched directly from API v1 metadata without client guessing.
2. **WMS Layers** (e.g. Moon Trek hillshade, slope, temperature):
   - Attached using `ol/layer/Image` with `ol/source/ImageWMS`.
   - Dynamic bounding box requests in specified projection bounds.
3. **Projections**:
   - Equirectangular (`IAU2000:30100` / sphere radius 1737.4 km) for global/equatorial sites.
   - Polar Stereographic (`IAU2000:30120` / South Pole) for Artemis landing sites (latitudes south of $-80^\circ$).
   - Configured through `proj4` definitions registered with OpenLayers.

---

## 5. Integration Steps for Application Shell (For Sasha)

To mount the components in `frontend/src/components/MapSlot.tsx` and `SceneSlot.tsx`:

1. **MapSlot**:
   ```tsx
   import { LunarMap } from '../features/map'

   export const MapSlot: React.FC<MapSlotProps> = ({
     selectedSiteId,
     targetCoordinates,
     onCoordinateSelect,
     className = '',
   }) => (
     <section className={`slot-container map-slot ${className}`} data-testid="map-slot">
       <div className="slot-header">
         <h3 className="slot-title">Lunar Surface Map</h3>
       </div>
       <div className="slot-body">
         <LunarMap
           selectedSiteId={selectedSiteId}
           selectedCoordinate={targetCoordinates}
           onSelectCoordinate={onCoordinateSelect}
         />
       </div>
     </section>
   )
   ```

2. **SceneSlot**:
   ```tsx
   import { LunarScene } from '../features/scene'

   export const SceneSlot: React.FC<SceneSlotProps> = ({
     sunDirectionEnu,
     earthDirectionEnu,
     observerHeightM = 2,
     className = '',
   }) => (
     <section className={`slot-container scene-slot ${className}`} data-testid="scene-slot">
       <div className="slot-header">
         <h3 className="slot-title">3D Local Terrain Scene</h3>
       </div>
       <div className="slot-body">
         <LunarScene
           sunDirectionEnu={sunDirectionEnu}
           earthDirectionEnu={earthDirectionEnu}
           observerHeightM={observerHeightM}
         />
       </div>
     </section>
   )
   ```
