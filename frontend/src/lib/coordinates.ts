/**
 * Lunar Coordinate Conventions and Vector Conversions
 *
 * Implements Stage 0 coordinate conventions for Lunar Landing Site Navigator:
 * - Longitude normalization to [-180, 180) degrees
 * - Latitude/Longitude to Moon-Centered Moon-Fixed (MCMF) unit vector
 * - Topocentric East-North-Up (ENU) to local Three.js scene coordinates
 * - Azimuth/Elevation to topocentric ENU unit vector
 * - Direction vector normalization and validation
 *
 * All functions are pure and perform no side effects.
 * No Earth dimensions or Earth geoids are used.
 */

import type { EnuVector } from '../components/types'

export type { EnuVector }

/**
 * 3D vector representation in Cartesian space.
 */
export interface Vector3D {
  x: number
  y: number
  z: number
}

/**
 * Lunar geographic coordinate in degrees.
 */
export interface LunarCoordinate {
  latitude: number
  longitude: number
}

/**
 * Tolerance for direction vector unit-length validation.
 * Uses 1e-4 tolerance to account for floating-point serialization differences.
 */
export const UNIT_VECTOR_TOLERANCE = 1e-4

/**
 * Normalizes input longitude to [-180, 180) degrees per API v1 specification:
 * `((longitude + 180) % 360) - 180`
 *
 * Handles negative JavaScript modulo behavior by computing true Euclidean modulo.
 *
 * @param longitude - Longitude in degrees, expected input in [-180, 360)
 * @returns Normalized longitude in [-180, 180)
 */
export function normalizeLongitude(longitude: number): number {
  if (!Number.isFinite(longitude)) {
    throw new TypeError(`Longitude must be a finite number, received: ${longitude}`)
  }
  // JavaScript % operator is remainder, not modulo: ((n % m) + m) % m gives true modulo.
  const shifted = longitude + 180.0
  const mod = ((shifted % 360.0) + 360.0) % 360.0
  const normalized = mod - 180.0

  // Guard against negative zero (-0)
  if (Object.is(normalized, -0)) {
    return 0.0
  }

  // Round to 6 decimal places to prevent IEEE 754 precision artifacts (e.g. 222.1 -> -137.9)
  const rounded = Math.round(normalized * 1e6) / 1e6
  return rounded >= 180 ? -180 : rounded
}

/**
 * Converts lunar latitude and longitude to a global Moon-Centered Moon-Fixed (MCMF) unit position.
 *
 * Documented Moon-fixed coordinate frame:
 * - +X: Intersection of lunar equator and prime meridian (latitude 0°, longitude 0°)
 * - +Y: Lunar equator at 90° East (latitude 0°, longitude +90°)
 * - +Z: Lunar North pole (latitude +90°)
 *
 * The Moon is represented as a unit sphere for directional geometry;
 * physical topography / elevation models are layered separately.
 *
 * @param coord - Lunar coordinate (latitude in [-90, 90], longitude in [-180, 360))
 * @returns Unit 3D vector in Moon-fixed Cartesian frame
 */
export function latLonToMoonFixedUnit(coord: LunarCoordinate): Vector3D {
  const { latitude, longitude } = coord

  if (!Number.isFinite(latitude) || latitude < -90.0 || latitude > 90.0) {
    throw new RangeError(`Latitude must be within [-90, 90] degrees, received: ${latitude}`)
  }

  const normLon = normalizeLongitude(longitude)
  const latRad = (latitude * Math.PI) / 180.0
  const lonRad = (normLon * Math.PI) / 180.0

  const cosLat = Math.cos(latRad)
  const sinLat = Math.sin(latRad)
  const cosLon = Math.cos(lonRad)
  const sinLon = Math.sin(lonRad)

  // Handle poles cleanly to avoid near-zero float noise
  const x = Math.abs(cosLat) < 1e-15 ? 0.0 : cosLat * cosLon
  const y = Math.abs(cosLat) < 1e-15 ? 0.0 : cosLat * sinLon
  const z = sinLat

  return {
    x: Math.round(x * 1e8) / 1e8,
    y: Math.round(y * 1e8) / 1e8,
    z: Math.round(z * 1e8) / 1e8,
  }
}

/**
 * Maps topocentric East-North-Up (ENU) unit direction to local Three.js scene direction.
 *
 * Agreed local scene coordinate conventions:
 * - scene.x = +east
 * - scene.y = +up
 * - scene.z = -north (Three.js camera looks down -Z by default, so North points forward)
 *
 * @param enu - Validated topocentric ENU unit vector
 * @returns 3D vector in local scene coordinates
 */
export function enuToLocalScene(enu: EnuVector): Vector3D {
  if (!isValidDirectionVector(enu)) {
    throw new Error(`Invalid ENU direction vector: expected unit length, received [${enu.east}, ${enu.north}, ${enu.up}]`)
  }

  return {
    x: enu.east,
    y: enu.up,
    z: -enu.north,
  }
}

/**
 * Maps local Three.js scene direction back to topocentric East-North-Up (ENU) vector.
 *
 * Inverse of enuToLocalScene:
 * - east = scene.x
 * - north = -scene.z
 * - up = scene.y
 *
 * @param scene - Validated 3D vector in local scene coordinates
 * @returns ENU vector
 */
export function localSceneToEnu(scene: Vector3D): EnuVector {
  const norm = Math.hypot(scene.x, scene.y, scene.z)
  if (!Number.isFinite(norm) || Math.abs(norm - 1.0) > UNIT_VECTOR_TOLERANCE) {
    throw new Error(`Invalid scene vector: expected unit length, received magnitude ${norm}`)
  }

  return {
    east: scene.x,
    north: -scene.z,
    up: scene.y,
  }
}

/**
 * Computes topocentric ENU direction vector from local azimuth and elevation angles.
 *
 * Conventions:
 * - azimuthDeg: 0° = North, 90° = East, 180° = South, 270° = West (clockwise from North)
 * - elevationDeg: 0° = local geometric horizon, +90° = zenith (straight up), -90° = nadir
 *
 * Properties:
 * - Zero elevation produces a horizontal direction (up = 0)
 * - Positive elevation produces upward direction (up > 0)
 *
 * @param azimuthDeg - Azimuth in degrees [0, 360)
 * @param elevationDeg - Elevation in degrees [-90, 90]
 * @returns Unit ENU vector
 */
export function azimuthElevationToEnu(azimuthDeg: number, elevationDeg: number): EnuVector {
  if (!Number.isFinite(azimuthDeg) || !Number.isFinite(elevationDeg)) {
    throw new TypeError('Azimuth and elevation must be finite numbers')
  }
  if (elevationDeg < -90.0 || elevationDeg > 90.0) {
    throw new RangeError(`Elevation must be in [-90, 90] degrees, received: ${elevationDeg}`)
  }

  const azRad = (azimuthDeg * Math.PI) / 180.0
  const elRad = (elevationDeg * Math.PI) / 180.0

  const cosEl = Math.cos(elRad)
  const sinEl = Math.sin(elRad)

  // East = sin(azimuth) * cos(elevation)
  // North = cos(azimuth) * cos(elevation)
  // Up = sin(elevation)
  const east = Math.sin(azRad) * cosEl
  const north = Math.cos(azRad) * cosEl
  const up = sinEl

  return {
    east: Math.round(east * 1e8) / 1e8,
    north: Math.round(north * 1e8) / 1e8,
    up: Math.round(up * 1e8) / 1e8,
  }
}

/**
 * Checks whether an ENU vector is a valid finite unit vector within tolerance.
 *
 * @param v - Vector to validate
 * @param tolerance - Maximum deviation from unit length (default: UNIT_VECTOR_TOLERANCE)
 */
export function isValidDirectionVector(
  v: EnuVector | Vector3D,
  tolerance = UNIT_VECTOR_TOLERANCE
): boolean {
  if (!v || typeof v !== 'object') {
    return false
  }

  const x = 'east' in v ? v.east : v.x
  const y = 'north' in v ? v.north : v.y
  const z = 'up' in v ? v.up : v.z

  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return false
  }

  const norm = Math.hypot(x, y, z)
  return Math.abs(norm - 1.0) <= tolerance
}

/**
 * Normalizes an arbitrary non-zero 3D vector to unit length.
 *
 * @param v - Input vector
 * @returns Unit-length vector
 */
export function normalizeVector(v: Vector3D): Vector3D {
  if (!Number.isFinite(v.x) || !Number.isFinite(v.y) || !Number.isFinite(v.z)) {
    throw new TypeError('Vector components must be finite numbers')
  }

  const norm = Math.hypot(v.x, v.y, v.z)
  if (norm < 1e-12) {
    throw new RangeError('Cannot normalize a zero-length or degenerate vector')
  }

  return {
    x: v.x / norm,
    y: v.y / norm,
    z: v.z / norm,
  }
}
