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
      northPoints: [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, -length)],
    }
  }, [length])

  const eastGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints(eastPoints), [eastPoints])
  const upGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints(upPoints), [upPoints])
  const northGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints(northPoints), [northPoints])

  return (
    <group data-testid="local-axes">
      {/* East: +X */}
      <primitive object={new THREE.Line(eastGeo, new THREE.LineBasicMaterial({ color: '#ff4d4f', linewidth: 2 }))} />
      {/* Up: +Y */}
      <primitive object={new THREE.Line(upGeo, new THREE.LineBasicMaterial({ color: '#52c41a', linewidth: 2 }))} />
      {/* North: -Z */}
      <primitive object={new THREE.Line(northGeo, new THREE.LineBasicMaterial({ color: '#1890ff', linewidth: 2 }))} />
    </group>
  )
}

/**
 * Horizon Reference:
 * Circular disc and ring at local tangent plane (y = 0).
 */
const HorizonReference: React.FC<{ radius?: number }> = ({ radius = 6 }) => {
  return (
    <group rotation={[-Math.PI / 2, 0, 0]} data-testid="horizon-reference">
      {/* Outer ring */}
      <mesh>
        <ringGeometry args={[radius - 0.05, radius, 64]} />
        <meshBasicMaterial color="#555555" side={THREE.DoubleSide} />
      </mesh>
      {/* Semi-transparent horizontal plane */}
      <mesh>
        <circleGeometry args={[radius, 64]} />
        <meshBasicMaterial color="#1f1f1f" transparent opacity={0.35} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

/**
 * Observer Marker:
 * Cylinder / sphere marker at observer height above ground.
 */
const ObserverMarker: React.FC<{ heightM?: number }> = ({ heightM = 2 }) => {
  // In Stage 0, observer is placed at topocentric origin with small visual offset
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
      sceneDirection.z * distance
    )
  }, [sceneDirection, distance])

  const lineGeo = useMemo(() => {
    return new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), targetPos])
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
            })
          )
        }
      />
      {/* Target body sphere */}
      <mesh position={targetPos}>
        <sphereGeometry args={[size, 24, 24]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

/**
 * Inner Scene Canvas Contents.
 */
const SceneContent: React.FC<LunarSceneProps> = ({
  sunDirectionEnu,
  earthDirectionEnu,
  observerHeightM = 2,
  visualScale = 1.0,
}) => {
  const distance = DEFAULT_VISUAL_DISTANCE * visualScale

  const validSunDirection = useMemo(() => {
    if (!sunDirectionEnu || !isValidDirectionVector(sunDirectionEnu)) return null
    return enuToLocalScene(sunDirectionEnu)
  }, [sunDirectionEnu])

  const validEarthDirection = useMemo(() => {
    if (!earthDirectionEnu || !isValidDirectionVector(earthDirectionEnu)) return null
    return enuToLocalScene(earthDirectionEnu)
  }, [earthDirectionEnu])

  return (
    <>
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 20, 10]} intensity={0.8} />

      <LocalAxes length={5} />
      <HorizonReference radius={6} />
      <ObserverMarker heightM={observerHeightM} />

      {validSunDirection && (
        <DirectionMarker
          sceneDirection={validSunDirection}
          distance={distance}
          color="#ffc53d"
          label="Sun"
          size={0.45}
        />
      )}

      {validEarthDirection && (
        <DirectionMarker
          sceneDirection={validEarthDirection}
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
 * Pure 3D Local Scene Component for Stage 0.
 *
 * Implements:
 * - Primitive geometry (local axes, horizon disc, observer marker, Sun/Earth rays)
 * - Strict separation of visual scaling from physical coordinates
 * - Demonstration mode banner when requested
 * - Full Error Boundary isolation for WebGL failures
 * - Loading indicator
 */
export const LunarScene: React.FC<LunarSceneProps> = (props) => {
  const { className = '', isLoading = false, demonstrationMode = false, onError } = props

  return (
    <div
      className={`lunar-scene-container ${className}`}
      data-testid="lunar-scene-container"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: '320px',
        backgroundColor: '#0a0a0c',
        borderRadius: '6px',
        overflow: 'hidden',
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
            backgroundColor: 'rgba(250, 173, 20, 0.2)',
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
          Loading lunar scene ephemeris...
        </div>
      )}

      {/* 3D WebGL Canvas with Error Isolation */}
      <SceneErrorBoundary onError={onError}>
        <Suspense fallback={<div style={{ color: '#888', padding: '1rem' }}>Initializing scene...</div>}>
          <Canvas
            camera={{ position: [8, 7, 12], fov: 45 }}
            style={{ width: '100%', height: '100%' }}
            data-testid="lunar-scene-canvas"
          >
            <SceneContent {...props} />
          </Canvas>
        </Suspense>
      </SceneErrorBoundary>
    </div>
  )
}
