import type { Layer } from '../../api/types'
import type { LunarCoordinate } from '../../lib/coordinates'
import { normalizeLongitude } from '../../lib/coordinates'

/**
 * Verified Lunar Map Layers from the official API v1 catalog (`contracts/catalog/map_layers.json`).
 *
 * All layers use verified lunar coordinate reference systems:
 * - Moon Trek: `urn:ogc:def:crs:EPSG::104903`
 * - LROC: `IAU2000:30100`
 *
 * Neither layer uses Earth EPSG:4326 or Earth Web Mercator (EPSG:3857).
 */
export const VERIFIED_MAP_LAYERS: Layer[] = [
  {
    id: 'LRO_WAC_Mosaic_Global_303ppd_v02',
    name: 'LRO WAC Global Mosaic v2',
    provider: 'moon_trek',
    service_type: 'wmts',
    crs_id: 'urn:ogc:def:crs:EPSG::104903',
    coordinate_units: 'degrees',
    extent: [-180, -90, 180, 90],
    attribution: 'NASA/GSFC/ASU LROC Team; tiles served by NASA/JPL Moon Trek.',
    source_url:
      'https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/WMTSCapabilities.xml',
    tile_matrix_set: 'default028mm',
    access_url_template:
      '/api/v1/map/layers/LRO_WAC_Mosaic_Global_303ppd_v02/tiles/{matrix}/{row}/{col}',
  },
  {
    id: 'luna_wac_roi_south_summer',
    name: 'LROC WAC South Pole Summer Mosaic',
    provider: 'lroc',
    service_type: 'wms',
    crs_id: 'IAU2000:30100',
    coordinate_units: 'degrees',
    extent: [-180, -90, 180, 90],
    attribution: 'NASA/GSFC/ASU LROC Team; cite Speyerer and Robinson (2013).',
    source_url: 'https://wms.im-ldi.com/?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1',
    tile_matrix_set: null,
    access_url_template:
      '/api/v1/map/layers/luna_wac_roi_south_summer/image?bbox={min_x},{min_y},{max_x},{max_y}&width={width}&height={height}',
  },
  {
    id: 'luna_wac_global',
    name: 'LROC WAC Global 100m/px',
    provider: 'lroc',
    service_type: 'wms',
    crs_id: 'IAU2000:30100',
    coordinate_units: 'degrees',
    extent: [-180, -90, 180, 90],
    attribution: 'NASA/GSFC/ASU LROC Team.',
    source_url: 'https://wms.im-ldi.com/?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1',
    tile_matrix_set: null,
    access_url_template:
      '/api/v1/map/layers/luna_wac_global/image?bbox={min_x},{min_y},{max_x},{max_y}&width={width}&height={height}',
  },
]

/**
 * Checks whether a lunar coordinate is within the valid coverage extent of a map layer.
 */
export function isCoordinateInLayerExtent(
  coord: LunarCoordinate,
  layer: Layer
): boolean {
  if (!coord || !layer || !Array.isArray(layer.extent) || layer.extent.length < 4) {
    return false
  }

  const normLon = normalizeLongitude(coord.longitude)
  const lat = coord.latitude
  const [minX, minY, maxX, maxY] = layer.extent

  return normLon >= minX && normLon <= maxX && lat >= minY && lat <= maxY
}

/**
 * Constructs the backend proxy URL for fetching a layer preview or tile image.
 */
export function buildLayerImageUrl(
  layer: Layer,
  apiBaseUrl: string,
  options?: {
    bbox?: { minX: number; minY: number; maxX: number; maxY: number }
    width?: number
    height?: number
    matrix?: string | number
    row?: number
    col?: number
  }
): string {
  const base = apiBaseUrl.replace(/\/+$/, '')

  if (layer.service_type === 'wmts') {
    const matrix = options?.matrix ?? '0'
    const row = options?.row ?? 0
    const col = options?.col ?? 0
    const template = layer.access_url_template
      .replace('{matrix}', String(matrix))
      .replace('{row}', String(row))
      .replace('{col}', String(col))
    return `${base}${template}`
  }

  // WMS
  const bbox = options?.bbox ?? {
    minX: layer.extent[0] ?? -180,
    minY: layer.extent[1] ?? -90,
    maxX: layer.extent[2] ?? 180,
    maxY: layer.extent[3] ?? 90,
  }
  const width = Math.min(1024, Math.max(1, options?.width ?? 512))
  const height = Math.min(1024, Math.max(1, options?.height ?? 256))

  const template = layer.access_url_template
    .replace('{min_x}', String(bbox.minX))
    .replace('{min_y}', String(bbox.minY))
    .replace('{max_x}', String(bbox.maxX))
    .replace('{max_y}', String(bbox.maxY))
    .replace('{width}', String(width))
    .replace('{height}', String(height))

  return `${base}${template}`
}
