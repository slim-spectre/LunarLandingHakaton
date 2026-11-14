import type { NowRequest, Site } from '../../api/types'

export interface ScenarioDraft {
  mode: 'catalog' | 'custom'
  site: Site | null
  name: string
  latitude: string
  longitude: string
  utcTime: string
  height: string
  margin: string
}

export function initialScenario(): ScenarioDraft {
  return {
    mode: 'catalog',
    site: null,
    name: '',
    latitude: '',
    longitude: '',
    utcTime: new Date().toISOString().slice(0, 19),
    height: '2',
    margin: '0',
  }
}

export function serializeUtc(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value))
    throw new Error('Choose a UTC date and time, with whole seconds.')
  const seconds = value.length === 16 ? value + ':00' : value
  const time = new Date(seconds + 'Z')
  if (
    !Number.isFinite(time.getTime()) ||
    time.toISOString().slice(0, 19) !== seconds
  )
    throw new Error('Choose a valid UTC date and time.')
  if (seconds < '2000-01-01T00:00:00' || seconds >= '2050-01-01T00:00:00')
    throw new Error(
      'Observation time must be from 2000-01-01 up to, but excluding, 2050-01-01 UTC.',
    )
  return seconds + 'Z'
}

function bounded(
  value: string,
  name: string,
  minimum: number,
  maximum: number,
  exclusive = false,
): number {
  const number = Number(value)
  if (
    !value.trim() ||
    !Number.isFinite(number) ||
    number < minimum ||
    (exclusive ? number >= maximum : number > maximum)
  ) {
    throw new Error(
      `${name} must be ${minimum} to ${maximum}${exclusive ? ' (upper bound excluded)' : ''}.`,
    )
  }
  return number
}

export function buildRequest(draft: ScenarioDraft): NowRequest {
  const target_time = serializeUtc(draft.utcTime)
  const observer_height_m = bounded(
    draft.height,
    'Observer height in metres',
    0,
    20,
  )
  const visibility_margin_deg = bounded(
    draft.margin,
    'Visibility margin in degrees',
    0,
    5,
  )
  if (draft.mode === 'catalog' && !draft.site)
    throw new Error('Select a catalog site or enter custom coordinates.')
  const site =
    draft.mode === 'catalog'
      ? { site_id: draft.site!.id }
      : {
          ...(draft.name.trim() ? { name: draft.name.trim() } : {}),
          latitude: bounded(draft.latitude, 'Latitude', -90, 90),
          longitude: bounded(draft.longitude, 'Longitude', -180, 360, true),
        }
  return {
    site,
    target_time,
    horizon_mode: 'geometric',
    observer_height_m,
    visibility_margin_deg,
  }
}
