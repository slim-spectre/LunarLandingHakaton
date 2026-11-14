import React, { Suspense, useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { enuToLocalScene, isValidDirectionVector } from '../../lib/coordinates'
import { SceneErrorBoundary } from './SceneErrorBoundary'
import type { LunarSceneProps } from './types'

/**
 * Visual scale multiplier for scene rendering (distance to Sun/Earth markers).
 * Kept strictly separated from physical coordinates.
 */
const DEFAULT_VISUAL_DISTANCE = 8.0

/**
 * Local 3D coordinate axes:
 * - East: +X (Red)
 * - Up: +Y (Green)
 * - North: -Z (Blue)
 */
const LocalAxes: React.FC<{ length?: number }> = ({ length = 5 }) => {
  const { eastPoints, upPoints, northPoints } = useMemo(() => {
    return {
      eastPoints: [new THREE.Vector3(0, 0, 0), new THREE.Vector3(length, 0, 0)],
      upPoints: [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, length, 0)],
      northPoints: [
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 0, -length),
      ],
    }
  }, [length])

  const eastGeo = useMemo(
    () => new THREE.BufferGeometry().setFromPoints(eastPoints),
    [eastPoints],
  )
  const upGeo = useMemo(
    () => new THREE.BufferGeometry().setFromPoints(upPoints),
    [upPoints],
  )
  const northGeo = useMemo(
    () => new THREE.BufferGeometry().setFromPoints(northPoints),
    [northPoints],
  )

  return (
    <group data-testid="local-axes">
      {/* East: +X */}
      <primitive
        object={
          new THREE.Line(
            eastGeo,
            new THREE.LineBasicMaterial({ color: '#ff4d4f', linewidth: 2 }),
          )
        }
      />
      {/* Up: +Y */}
      <primitive
        object={
          new THREE.Line(
            upGeo,
            new THREE.LineBasicMaterial({ color: '#52c41a', linewidth: 2 }),
          )
        }
      />
      {/* North: -Z */}
      <primitive
        object={
          new THREE.Line(
            northGeo,
            new THREE.LineBasicMaterial({ color: '#1890ff', linewidth: 2 }),
          )
        }
      />
    </group>
  )
}

/**
 * Geometric Horizon Reference:
 * Circular disc and wireframe ring at local tangent plane (y = 0).
 * Clearly represents geometric horizon at 0.0° threshold (no terrain occlusion).
 */
const GeometricHorizonReference: React.FC<{ radius?: number }> = ({
  radius = 6,
}) => {
  return (
    <group rotation={[-Math.PI / 2, 0, 0]} data-testid="horizon-reference">
      {/* Outer horizon ring */}
      <mesh>
        <ringGeometry args={[radius - 0.05, radius, 64]} />
        <meshBasicMaterial color="#555555" side={THREE.DoubleSide} />
      </mesh>
      {/* Semi-transparent horizontal plane (y = 0) */}
      <mesh>
        <circleGeometry args={[radius, 64]} />
        <meshBasicMaterial
          color="#1f1f1f"
          transparent
          opacity={0.35}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  )
}

/**
 * Observer Marker:
 * Cylinder / sphere marker at observer height above ground.
 */
const ObserverMarker: React.FC<{ heightM?: number }> = ({ heightM = 2 }) => {
  const visualHeight = Math.max(0.1, Math.min(heightM * 0.2, 1.5))

  return (
    <group position={[0, visualHeight / 2, 0]} data-testid="observer-marker">
      <mesh>
        <cylinderGeometry args={[0.08, 0.08, visualHeight, 16]} />
        <meshStandardMaterial color="#d9d9d9" roughness={0.3} />
      </mesh>
      <mesh position={[0, visualHeight / 2 + 0.1, 0]}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color="#ffffff" roughness={0.2} />
      </mesh>
    </group>
  )
}

/**
 * Direction Marker:
 * Visual ray and spherical body marker for celestial directions (Sun / Earth).
 */
const DirectionMarker: React.FC<{
  sceneDirection: { x: number; y: number; z: number }
  distance: number
  color: string
  label: string
  size?: number
}> = ({ sceneDirection, distance, color, label, size = 0.35 }) => {
  const targetPos = useMemo(() => {
    return new THREE.Vector3(
      sceneDirection.x * distance,
      sceneDirection.y * distance,
      sceneDirection.z * distance,
    )
  }, [sceneDirection, distance])

  const lineGeo = useMemo(() => {
    return new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      targetPos,
    ])
  }, [targetPos])

  return (
    <group data-testid={`direction-marker-${label.toLowerCase()}`}>
      {/* Direction ray */}
      <primitive
        object={
          new THREE.Line(
            lineGeo,
            new THREE.LineDashedMaterial({
              color,
              dashSize: 0.3,
              gapSize: 0.15,
            }),
          )
        }
      />
      {/* Target body sphere */}
      <mesh position={targetPos}>
        <sphereGeometry args={[size, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.6}
        />
      </mesh>
    </group>
  )
}

/**
 * Inner Scene Canvas Contents.
 */
const SceneContent: React.FC<{
  sunDirection: { x: number; y: number; z: number } | null
  earthDirection: { x: number; y: number; z: number } | null
  observerHeightM: number
  visualScale: number
}> = ({ sunDirection, earthDirection, observerHeightM, visualScale }) => {
  const distance = DEFAULT_VISUAL_DISTANCE * visualScale

  return (
    <>
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 20, 10]} intensity={0.8} />

      <LocalAxes length={5} />
      <GeometricHorizonReference radius={6} />
      <ObserverMarker heightM={observerHeightM} />

      {sunDirection && (
        <DirectionMarker
          sceneDirection={sunDirection}
          distance={distance}
          color="#ffc53d"
          label="Sun"
          size={0.45}
        />
      )}

      {earthDirection && (
        <DirectionMarker
          sceneDirection={earthDirection}
          distance={distance}
          color="#4096ff"
          label="Earth"
          size={0.35}
        />
      )}
    </>
  )
}

/**
 * Pure 3D Local Scene Component for Stage 1.
 *
 * Implements:
 * - Real direction ENU vectors mapped to Three.js scene (x=east, y=up, z=-north)
 * - Strict separation of visual scaling from physical coordinates
 * - Observer marker & clearly labelled geometric horizon reference
 * - Azimuth and elevation labels agreeing with marker position above/below horizon
 * - Full Error Boundary isolation for WebGL failures
 * - Preserved observation timestamps and cache status display
 */
export const LunarScene: React.FC<LunarSceneProps> = (props) => {
  const {
    className = '',
    sunDirectionEnu,
    earthDirectionEnu,
    observationPoint,
    observerHeightM = 2,
    isLoading = false,
    dataStatus,
    timestamp,
    visualScale = 1.0,
    demonstrationMode = false,
    onError,
  } = props

  // Resolve effective Sun and Earth ENU vectors from observationPoint or direct props
  const effectiveSunEnu = useMemo(() => {
    return observationPoint?.sun.direction_enu ?? sunDirectionEnu ?? null
  }, [observationPoint, sunDirectionEnu])

  const effectiveEarthEnu = useMemo(() => {
    return observationPoint?.earth.direction_enu ?? earthDirectionEnu ?? null
  }, [observationPoint, earthDirectionEnu])

  const effectiveTimestamp = observationPoint?.timestamp ?? timestamp ?? null

  // Convert valid ENU vectors to local scene coordinates
  const validSunScene = useMemo(() => {
    if (!effectiveSunEnu || !isValidDirectionVector(effectiveSunEnu))
      return null
    return enuToLocalScene(effectiveSunEnu)
  }, [effectiveSunEnu])

  const validEarthScene = useMemo(() => {
    if (!effectiveEarthEnu || !isValidDirectionVector(effectiveEarthEnu))
      return null
    return enuToLocalScene(effectiveEarthEnu)
  }, [effectiveEarthEnu])

  // Scientific labels and flags come only from the observation response.
  const sunAngles = observationPoint
    ? {
        azimuth: observationPoint.sun.azimuth_deg,
        elevation: observationPoint.sun.elevation_deg,
        visible: observationPoint.sun.visible,
      }
    : null
  const earthAngles = observationPoint
    ? {
        azimuth: observationPoint.earth.azimuth_deg,
        elevation: observationPoint.earth.elevation_deg,
        visible: observationPoint.earth.visible,
      }
    : null

  return (
    <div
      className={`lunar-scene-container ${className}`}
      data-testid="lunar-scene-container"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '340px',
        backgroundColor: '#0a0a0c',
        borderRadius: '6px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Demonstration Banner */}
      {demonstrationMode && (
        <div
          data-testid="demonstration-banner"
          style={{
            position: 'absolute',
            top: '8px',
            left: '8px',
            zIndex: 10,
            padding: '4px 8px',
            backgroundColor: 'rgba(250, 173, 20, 0.25)',
            border: '1px solid #faad14',
            borderRadius: '4px',
            color: '#faad14',
            fontSize: '0.75rem',
            fontWeight: 600,
          }}
        >
          Demonstration Vectors Only — Not Measured Ephemeris
        </div>
      )}

      {/* Top HUD Status & Angle Labels */}
      <div
        className="scene-hud-overlay"
        data-testid="scene-hud-overlay"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          padding: '6px 10px',
          backgroundColor: 'rgba(10, 10, 12, 0.85)',
          borderBottom: '1px solid #1f2029',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '6px',
          fontSize: '0.75rem',
          color: '#a0a0a0',
          zIndex: 9,
        }}
      >
        <div style={{ display: 'flex', gap: '12px' }}>
          {sunAngles ? (
            <span data-testid="hud-sun-label" style={{ color: '#ffc53d' }}>
              <strong>Sun:</strong> Az {sunAngles.azimuth.toFixed(1)}° · El{' '}
              {sunAngles.elevation.toFixed(1)}° (
              {sunAngles.visible ? 'Visible' : 'Not visible'})
            </span>
          ) : (
            <span style={{ color: '#777' }}>Sun: Awaiting vector</span>
          )}

          {earthAngles ? (
            <span data-testid="hud-earth-label" style={{ color: '#4096ff' }}>
              <strong>Earth:</strong> Az {earthAngles.azimuth.toFixed(1)}° · El{' '}
              {earthAngles.elevation.toFixed(1)}° (
              {earthAngles.visible ? 'Visible' : 'Not visible'})
            </span>
          ) : (
            <span style={{ color: '#777' }}>Earth: Awaiting vector</span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {effectiveTimestamp && (
            <span style={{ color: '#aaa', fontSize: '0.7rem' }}>
              {effectiveTimestamp}
              {dataStatus === 'cached' && (
                <span
                  style={{
                    marginLeft: '4px',
                    padding: '1px 4px',
                    backgroundColor: 'rgba(24, 144, 255, 0.2)',
                    borderRadius: '2px',
                    color: '#1890ff',
                    fontSize: '0.65rem',
                  }}
                >
                  cached
                </span>
              )}
            </span>
          )}
        </div>
      </div>

      {/* 3D WebGL Canvas with Error Isolation */}
      <div style={{ position: 'relative', flex: 1, width: '100%' }}>
        <SceneErrorBoundary onError={onError}>
          <Suspense
            fallback={
              <div style={{ color: '#888', padding: '1rem' }}>
                Initializing scene…
              </div>
            }
          >
            <Canvas
              camera={{ position: [8, 7, 12], fov: 45 }}
              style={{ width: '100%', height: '100%' }}
              data-testid="lunar-scene-canvas"
            >
              <SceneContent
                sunDirection={validSunScene}
                earthDirection={validEarthScene}
                observerHeightM={observerHeightM}
                visualScale={visualScale}
              />
            </Canvas>
          </Suspense>
        </SceneErrorBoundary>
      </div>

      {/* Bottom Terrain Reference Notice */}
      <div
        className="scene-horizon-notice"
        data-testid="scene-horizon-notice"
        style={{
          padding: '4px 10px',
          backgroundColor: '#0c0d12',
          borderTop: '1px solid #1a1a24',
          fontSize: '0.65rem',
          color: '#656575',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>
          Geometric Reference Horizon (Elevation 0.0°) · Local ENU scene
        </span>
        <span>Terrain occlusion not modeled in Stage 1</span>
      </div>

      {/* Loading Overlay */}
      {isLoading && (
        <div
          data-testid="scene-loading-overlay"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(10, 10, 12, 0.75)',
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#d9d9d9',
            fontSize: '0.9rem',
          }}
        >
          Loading lunar scene ephemeris…
        </div>
      )}
    </div>
  )
}
