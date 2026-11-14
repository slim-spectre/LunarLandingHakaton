import { describe, it, expect } from 'vitest'
import {
  normalizeLongitude,
  latLonToMoonFixedUnit,
  enuToLocalScene,
  localSceneToEnu,
  azimuthElevationToEnu,
  isValidDirectionVector,
  normalizeVector,
} from './coordinates'

describe('coordinates library', () => {
  describe('normalizeLongitude', () => {
    it('normalizes longitude 222.1 to -137.9', () => {
      expect(normalizeLongitude(222.1)).toBe(-137.9)
    })

    it('preserves values already within [-180, 180)', () => {
      expect(normalizeLongitude(0)).toBe(0)
      expect(normalizeLongitude(45.5)).toBe(45.5)
      expect(normalizeLongitude(-120.25)).toBe(-120.25)
      expect(normalizeLongitude(-180)).toBe(-180)
      expect(normalizeLongitude(179.999)).toBe(179.999)
    })

    it('wraps 180 to -180 per half-open interval [-180, 180)', () => {
      expect(normalizeLongitude(180)).toBe(-180)
    })

    it('handles negative longitudes requiring wrap-around', () => {
      expect(normalizeLongitude(-190)).toBe(170)
      expect(normalizeLongitude(-270)).toBe(90)
    })

    it('handles multiples of 360 degrees', () => {
      expect(normalizeLongitude(360)).toBe(0)
      expect(normalizeLongitude(720)).toBe(0)
      expect(normalizeLongitude(-360)).toBe(0)
    })

    it('rejects non-finite values', () => {
      expect(() => normalizeLongitude(Number.NaN)).toThrow(TypeError)
      expect(() => normalizeLongitude(Number.POSITIVE_INFINITY)).toThrow(TypeError)
    })
  })

  describe('latLonToMoonFixedUnit', () => {
    it('maps equator and prime meridian (0, 0) to +X', () => {
      const pos = latLonToMoonFixedUnit({ latitude: 0, longitude: 0 })
      expect(pos.x).toBeCloseTo(1, 6)
      expect(pos.y).toBeCloseTo(0, 6)
      expect(pos.z).toBeCloseTo(0, 6)
    })

    it('maps equator at 90 deg East (0, 90) to +Y', () => {
      const pos = latLonToMoonFixedUnit({ latitude: 0, longitude: 90 })
      expect(pos.x).toBeCloseTo(0, 6)
      expect(pos.y).toBeCloseTo(1, 6)
      expect(pos.z).toBeCloseTo(0, 6)
    })

    it('maps lunar North pole (90, 0) to +Z', () => {
      const pos = latLonToMoonFixedUnit({ latitude: 90, longitude: 0 })
      expect(pos.x).toBeCloseTo(0, 6)
      expect(pos.y).toBeCloseTo(0, 6)
      expect(pos.z).toBeCloseTo(1, 6)
    })

    it('maps lunar South pole (-90, 0) to -Z', () => {
      const pos = latLonToMoonFixedUnit({ latitude: -90, longitude: 0 })
      expect(pos.x).toBeCloseTo(0, 6)
      expect(pos.y).toBeCloseTo(0, 6)
      expect(pos.z).toBeCloseTo(-1, 6)
    })

    it('preserves unit-length and numerical stability at high lunar latitudes', () => {
      // Shackleton rim: latitude -89.44, longitude 222.1
      const shackleton = latLonToMoonFixedUnit({ latitude: -89.44, longitude: 222.1 })
      const norm = Math.hypot(shackleton.x, shackleton.y, shackleton.z)
      expect(norm).toBeCloseTo(1.0, 6)
      expect(shackleton.z).toBeLessThan(-0.999) // strongly pointing toward south pole
      expect(Number.isFinite(shackleton.x)).toBe(true)
      expect(Number.isFinite(shackleton.y)).toBe(true)

      // Extreme high latitude -89.999
      const extreme = latLonToMoonFixedUnit({ latitude: -89.999, longitude: 45.0 })
      const extremeNorm = Math.hypot(extreme.x, extreme.y, extreme.z)
      expect(extremeNorm).toBeCloseTo(1.0, 6)
    })

    it('rejects latitude outside [-90, 90]', () => {
      expect(() => latLonToMoonFixedUnit({ latitude: 95, longitude: 0 })).toThrow(RangeError)
      expect(() => latLonToMoonFixedUnit({ latitude: -91, longitude: 0 })).toThrow(RangeError)
    })
  })

  describe('enuToLocalScene and localSceneToEnu (cardinal directions)', () => {
    it('maps cardinal East (1, 0, 0) to scene (1, 0, 0)', () => {
      const east = enuToLocalScene({ east: 1, north: 0, up: 0 })
      expect(east).toEqual({ x: 1, y: 0, z: -0 })
    })

    it('maps cardinal North (0, 1, 0) to scene (0, 0, -1)', () => {
      const north = enuToLocalScene({ east: 0, north: 1, up: 0 })
      expect(north).toEqual({ x: 0, y: 0, z: -1 })
    })

    it('maps cardinal Up (0, 0, 1) to scene (0, 1, 0)', () => {
      const up = enuToLocalScene({ east: 0, north: 0, up: 1 })
      expect(up).toEqual({ x: 0, y: 1, z: -0 })
    })

    it('is reversible with localSceneToEnu', () => {
      const original = { east: 0.6, north: 0.8, up: 0 }
      const scene = enuToLocalScene(original)
      const reverted = localSceneToEnu(scene)
      expect(reverted.east).toBeCloseTo(original.east, 6)
      expect(reverted.north).toBeCloseTo(original.north, 6)
      expect(reverted.up).toBeCloseTo(original.up, 6)
    })

    it('rejects non-unit or invalid ENU vectors in enuToLocalScene', () => {
      expect(() => enuToLocalScene({ east: 2, north: 0, up: 0 })).toThrow()
      expect(() => enuToLocalScene({ east: 0, north: 0, up: 0 })).toThrow()
      expect(() => enuToLocalScene({ east: Number.NaN, north: 0, up: 0 })).toThrow()
    })
  })

  describe('azimuthElevationToEnu', () => {
    it('produces a horizontal direction with up = 0 for zero elevation', () => {
      // Due North (azimuth 0, elevation 0)
      const northHorizontal = azimuthElevationToEnu(0, 0)
      expect(northHorizontal.up).toBe(0)
      expect(northHorizontal.north).toBeCloseTo(1, 6)
      expect(northHorizontal.east).toBeCloseTo(0, 6)

      // Due East (azimuth 90, elevation 0)
      const eastHorizontal = azimuthElevationToEnu(90, 0)
      expect(eastHorizontal.up).toBe(0)
      expect(eastHorizontal.east).toBeCloseTo(1, 6)
      expect(eastHorizontal.north).toBeCloseTo(0, 6)

      // Arbitrary azimuth with zero elevation
      const arbitrary = azimuthElevationToEnu(137.5, 0)
      expect(arbitrary.up).toBe(0)
      const norm = Math.hypot(arbitrary.east, arbitrary.north, arbitrary.up)
      expect(norm).toBeCloseTo(1.0, 6)
    })

    it('points upward with positive up for positive elevation', () => {
      const elevated = azimuthElevationToEnu(45, 30)
      expect(elevated.up).toBeGreaterThan(0)
      expect(elevated.up).toBeCloseTo(0.5, 6) // sin(30) = 0.5

      const zenith = azimuthElevationToEnu(0, 90)
      expect(zenith.up).toBeCloseTo(1.0, 6)
      expect(zenith.east).toBeCloseTo(0, 6)
      expect(zenith.north).toBeCloseTo(0, 6)
    })

    it('rejects invalid elevation angles', () => {
      expect(() => azimuthElevationToEnu(0, 91)).toThrow(RangeError)
      expect(() => azimuthElevationToEnu(0, -91)).toThrow(RangeError)
    })
  })

  describe('vector normalization and validation', () => {
    it('preserves unit length on valid vectors', () => {
      const v = { x: 3, y: 0, z: 4 }
      const unit = normalizeVector(v)
      expect(Math.hypot(unit.x, unit.y, unit.z)).toBeCloseTo(1.0, 6)
      expect(unit.x).toBeCloseTo(0.6, 6)
      expect(unit.y).toBeCloseTo(0.0, 6)
      expect(unit.z).toBeCloseTo(0.8, 6)
    })

    it('rejects zero-length vectors in normalizeVector', () => {
      expect(() => normalizeVector({ x: 0, y: 0, z: 0 })).toThrow(RangeError)
    })

    it('validates unit vectors correctly with isValidDirectionVector', () => {
      expect(isValidDirectionVector({ east: 1, north: 0, up: 0 })).toBe(true)
      expect(isValidDirectionVector({ x: 0, y: 1, z: 0 })).toBe(true)
      expect(isValidDirectionVector({ east: 0.6, north: 0.8, up: 0 })).toBe(true)

      // Non-unit vectors
      expect(isValidDirectionVector({ east: 1.1, north: 0, up: 0 })).toBe(false)
      expect(isValidDirectionVector({ east: 0, north: 0, up: 0 })).toBe(false)

      // NaNs and infinities
      expect(isValidDirectionVector({ east: Number.NaN, north: 0, up: 0 })).toBe(false)
      expect(isValidDirectionVector({ east: 1, north: Number.POSITIVE_INFINITY, up: 0 })).toBe(false)
    })
  })
})
