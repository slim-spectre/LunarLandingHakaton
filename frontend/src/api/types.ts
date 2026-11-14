/**
 * Shared API contract types.
 *
 * Generated directly from contracts/openapi.v1.yaml via openapi-typescript.
 * Do not edit or create a secondary schema manually.
 */

import type { components, paths, operations } from './generated/schema'

export type Health = components['schemas']['Health']
export type ErrorEnvelope = components['schemas']['ErrorEnvelope']
export type ApiError = components['schemas']['Error']
export type ErrorDetail = components['schemas']['ErrorDetail']

export type Site = components['schemas']['Site']
export type SiteList = components['schemas']['SiteList']
export type ResolvedSite = components['schemas']['ResolvedSite']
export type SiteInput = components['schemas']['SiteInput']

export type Layer = components['schemas']['Layer']
export type LayerList = components['schemas']['LayerList']

export type TerrainCoverage = components['schemas']['TerrainCoverage']
export type Heightmap = components['schemas']['Heightmap']

export type CSAResources = components['schemas']['CSAResources']
export type CSAItem = components['schemas']['CSAItem']

export type NowRequest = components['schemas']['NowRequest']
export type NowResult = components['schemas']['NowResult']

export type JobAccepted = components['schemas']['JobAccepted']
export type Job = components['schemas']['Job']

export type { components, paths, operations }
