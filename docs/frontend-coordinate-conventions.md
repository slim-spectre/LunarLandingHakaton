# Frontend Coordinate Conventions and Map/Scene Integration

Documented conventions, coordinate frames, axis signs, units, component props, and integration instructions for the map and 3D local scene in **Stage 1**.

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

| ENU Vector | Direction | Three.js Scene Coordinate | Elevation / Horizon Agreement |
| :--- | :--- | :--- | :--- |
| $[1, 0, 0]$ | East | $[1, 0, 0]$ | $\text{el} = 0^\circ \implies \text{scene.y} = 0$ (on horizon) |
| $[0, 1, 0]$ | North | $[0, 0, -1]$ | $\text{el} = 0^\circ \implies \text{scene.y} = 0$ (on horizon) |
| $[0, 0, 1]$ | Up / Zenith | $[0, 1, 0]$ | $\text{el} = +90^\circ \implies \text{scene.y} > 0$ (above horizon) |
| $[-1, 0, 0]$ | West | $[-1, 0, 0]$ | $\text{el} = 0^\circ \implies \text{scene.y} = 0$ (on horizon) |
| $[0, -1, 0]$ | South | $[0, 0, 1]$ | $\text{el} = 0^\circ \implies \text{scene.y} = 0$ (on horizon) |
| $[0, 0, -1]$ | Down / Nadir | $[0, -1, 0]$ | $\text{el} = -90^\circ \implies \text{scene.y} < 0$ (below horizon) |

Visual scaling (such as marker distance multipliers or observer height exaggeration) is maintained strictly separate from underlying physical coordinates.

---

## 2. Units and Angular Conventions

- **Latitude**: Decimal degrees in $[-90.0, 90.0]$.
- **Longitude**: Input accepted in $[-180.0, 360.0)$; normalized to $[-180.0, 180.0)$ using:
  $$\text{normalized} = ((\text{longitude} + 180) \bmod 360) - 180$$
- **Azimuth**: Decimal degrees in $[0.0, 360.0)$, measured clockwise from North ($0^\circ = \text{North}$, $90^\circ = \text{East}$, $180^\circ = \text{South}$, $270^\circ = \text{West}$).
- **Elevation**: Decimal degrees in $[-90.0, 90.0]$ relative to the local horizontal tangent plane ($0^\circ = \text{horizon}$, $+90^\circ = \text{zenith}$, $-90^\circ = \text{nadir}$).
  - Zero elevation produces a strictly horizontal vector ($\text{up} = 0 \implies \text{scene.y} = 0$).
  - Positive elevation points upward ($\text{up} > 0 \implies \text{scene.y} > 0$).
  - Negative elevation points downward ($\text{up} < 0 \implies \text{scene.y} < 0$).
- **Observer Height**: Metres above base model surface (default: $2.0\,\text{m}$, allowed range: $0$--$20\,\text{m}$).

---

## 3. Verified Map Layers (Stage 1)

The backend provides verified lunar map services via `/api/v1/map/layers`:

| Layer ID | Provider | Type | CRS | Units | Attribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `LRO_WAC_Mosaic_Global_303ppd_v02` | `moon_trek` | WMTS | `urn:ogc:def:crs:EPSG::104903` | degrees | NASA/GSFC/ASU LROC Team; tiles served by NASA/JPL Moon Trek. |
| `luna_wac_roi_south_summer` | `lroc` | WMS | `IAU2000:30100` | degrees | NASA/GSFC/ASU LROC Team; cite Speyerer and Robinson (2013). |
| `luna_wac_global` | `lroc` | WMS | `IAU2000:30100` | degrees | NASA/GSFC/ASU LROC Team. |

### Map Layer Rules:
- Lunar CRS: Do NOT assume Earth Web Mercator (EPSG:3857) or Earth WGS84 (EPSG:4326).
- Attribution: Every layer displays its official verbatim attribution and source GetCapabilities link.
- QuickMap: When a catalog site carries a verified `quickmap_url`, it is presented directly without inventing query parameters.
- Missing Imagery: Network errors or provider 502/503 responses display an explicit provider failure banner, never presenting missing imagery as valid terrain coverage.

---

## 4. Component Interfaces and Props

### 4.1 `LunarMap` (`frontend/src/features/map/`)
```typescript
export interface LunarMapProps {
  className?: string
  /** Selected lunar coordinate (latitude [-90, 90], longitude [-180, 180)) */
  selectedCoordinate?: LunarCoordinate | null
  /** Callback triggered when user clicks or selects a point on the map */
  onSelectCoordinate?: (coord: LunarCoordinate) => void
  /** Optional ID of selected catalog landing site */
  selectedSiteId?: string | null
  /** Verified QuickMap reference link from site catalog */
  quickmapUrl?: string | null
  /** Currently active map layer identifier */
  activeLayerId?: string
  /** Callback invoked when user switches map layers */
  onLayerChange?: (layerId: string) => void
  /** Optional custom layers list (defaults to verified Moon Trek & LROC catalog) */
  layers?: Layer[]
  /** Loading state flag */
  isLoading?: boolean
  /** Unavailable state flag */
  isUnavailable?: boolean
  /** Reason for unavailability displayed to user */
  unavailableReason?: string
}
```

### 4.2 `LunarScene` (`frontend/src/features/scene/`)
```typescript
export interface LunarSceneProps {
  className?: string
  /** Topocentric ENU unit direction toward Sun (null if uncalculated or unavailable) */
  sunDirectionEnu?: EnuVector | null
  /** Topocentric ENU unit direction toward Earth (null if uncalculated or unavailable) */
  earthDirectionEnu?: EnuVector | null
  /** Direct observation point matching canonical API contract */
  observationPoint?: ObservationPoint | null
  /** Resolved or catalog site */
  site?: ResolvedSite | Site | null
  /** Observer height in metres above surface (default: 2.0) */
  observerHeightM?: number
  /** Loading state flag */
  isLoading?: boolean
  /** Data freshness status from result metadata ('fresh' | 'cached') */
  dataStatus?: 'fresh' | 'cached' | null
  /** Explicit requested observation timestamp */
  timestamp?: string | null
  /** Reserved for Stage 2 physical terrain elevation heightmap */
  heightmap?: unknown | null
  /** Visual scale multiplier for rendering distance (separated from physical coords) */
  visualScale?: number
  /** When true, displays explicit 'Demonstration Vectors Only' banner */
  demonstrationMode?: boolean
  /** Callback on WebGL / rendering error */
  onError?: (error: Error) => void
}
```

### 4.3 Error Isolation
`SceneErrorBoundary` isolates WebGL and Three.js runtime crashes:
- Prevents scene failures from unmounting forms, numerical results, or the application shell.
- Provides a clean localized fallback message with a "Retry 3D Scene" action.
- Uses zero mandatory external textures.

---

## 5. Terrain Boundary Notice (Stage 1 vs Stage 2)

- **Stage 1 (Current)**:
  - The scene operates strictly with a **geometric horizon reference plane** ($0.0^\circ$ elevation threshold).
  - No physical terrain occlusion or crater-wall ray tracing is claimed or modeled.
  - Bump maps and hillshade textures are never interpreted as numerical terrain geometry.
- **Stage 2 (Upcoming)**:
  - High-resolution DEM heightmaps (e.g. PGDA products for Shackleton, Faustini) will attach via the prepared `heightmap` prop and compute numerical line-of-sight obstruction.
