# Lunar Landing Site Navigator — Frontend Foundation (Stage 0)

This is the frontend application and API integration foundation for the Lunar Landing Site Navigator.

## Node & Package Manager Baseline

- **Node Baseline:** `22.13.0` (matching `.nvmrc` at repository root; Node 22.13 or newer supported).
- **Package Manager:** `npm` (with locked, reproducible `package-lock.json`).

## Environment Variables

Configure environment variables in a local `.env` file within `frontend/` or repository root:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | Backend API v1 base URL. Normalizes trailing slashes automatically. |
| `VITE_USE_CONTRACT_MOCKS` | `false` | Explicit development-only fixture mode. Never active in production builds. Displays an unmistakable `DEMO / TEST DATA` badge when active. |

## Quick Start

```sh
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
npm run dev
```

The dev server starts on `http://localhost:5173/`.

## Available Scripts

- `npm run dev`: Starts the Vite development server with HMR.
- `npm run build`: Typechecks with `tsc -b` and builds optimized production assets in `dist/`.
- `npm run lint`: Runs fast code linting via `oxlint`.
- `npm run typecheck`: Runs TypeScript project compilation check (`tsc -b`).
- `npm run test`: Runs automated unit and component test suite via `vitest run`.
- `npm run test:watch`: Runs Vitest in interactive watch mode.
- `npm run generate:api`: Regenerates TypeScript types from `../contracts/openapi.v1.yaml` into `src/api/generated/schema.ts`.
- `npm run check:api`: Detects schema drift by verifying that generated types are up to date with `contracts/openapi.v1.yaml`. Fails with non-zero exit code on drift.

## Architecture & Module Scope

- `src/api/`:
  - `generated/schema.ts`: Auto-generated from `contracts/openapi.v1.yaml`.
  - `types.ts`: Re-exported contract types without secondary schema duplication.
  - `errors.ts`: `ApiClientError` class parsing the agreed `{ error: { code, message, details, request_id } }` envelope.
  - `client.ts`: Shared API client with timeout, abort handling, base URL resolution, and GET `/api/v1/health`. Strictly avoids synthetic data fallbacks on real failures.
  - `mocks.ts`: Synthetic development fixtures strictly from `contracts/examples/`.
- `src/features/health/`:
  - `HealthCard.tsx`: Backend health indicator with loading state, healthy state (200), database failure state (503), and network unreachable state.
  - `useHealth.ts`: Initial loading state hook querying `/api/v1/health`.
- `src/components/`:
  - `MapSlot.tsx`: Reserved slot for lunar surface map with lunar projection support.
  - `SceneSlot.tsx`: Reserved slot for 3D local terrain scene.
  - `AnalyticsSlot.tsx`: Reserved slot for visibility timeline and solar analytics (Stage 1).
  - `types.ts`: Shared coordinate types and slot interfaces.

## Slavik Handoff Interface

Slavik owns the map, 3D scene, and coordinate-transformation modules. The foundation pre-installs and prepares the required dependencies and provides typed integration slots:

### 1. Pre-installed Dependencies

- **3D Scene:** `three` (`^0.187.0`), `@react-three/fiber` (`^9.8.2`), `@types/three`.
- **Planetary Mapping:** `ol` (`^10.11.0` - OpenLayers), `proj4` (`^2.23.0`), `@types/proj4`.

### 2. Agreed Coordinate Convention (`EnuVector`)

Topocentric East-North-Up unit direction vector agreed in `src/components/types.ts`:

```typescript
export interface EnuVector {
  east: number;
  north: number;
  up: number;
}
```

- Units: unit direction vectors (no display distance multiplier).
- Tangent plane: East = +X, North = +Y, Up = +Z.

### 3. Integration Slots

- `MapSlot` (`src/components/MapSlot.tsx`): Integrates OpenLayers WMS/WMTS with custom lunar projections (Moon Trek / LROC).
- `SceneSlot` (`src/components/SceneSlot.tsx`): Integrates Three.js / R3F with local heightmap mesh and Sun/Earth ENU direction vectors.

The generated API schema uses LF line endings (enforced by root .gitattributes),
because check:api compares generated and committed files byte for byte. After a
contract change, run npm run generate:api and review the generated diff. CI runs
lint, check:api, tests and build on the pinned Node version.
