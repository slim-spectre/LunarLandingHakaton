import { describe, expect, it } from 'vitest'
import { buildRequest, initialScenario, serializeUtc } from './scenario'
import { catalog } from '../../test/fixtures'

describe('UTC scenario validation', () => {
  it('serializes UTC explicitly without a browser-local conversion', () => {
    expect(serializeUtc('2027-07-15T12:34')).toBe('2027-07-15T12:34:00Z')
    expect(serializeUtc('2027-07-15T12:34:56')).toBe('2027-07-15T12:34:56Z')
    expect(serializeUtc('2000-01-01T00:00:00')).toBe('2000-01-01T00:00:00Z')
    expect(serializeUtc('2049-12-31T23:59:59')).toBe('2049-12-31T23:59:59Z')
  })
  it.each([
    '1999-12-31T23:59:59',
    '2050-01-01T00:00',
    '2027-02-29T00:00',
    '2027-07-15T24:00',
    '2027-07-15T00:00:00.001',
    '',
    '2027-07-15T00:00Z',
  ])('rejects invalid or unsupported UTC input %s', (value) => {
    expect(() => serializeUtc(value)).toThrow()
  })
  it('keeps the two site input forms mutually exclusive', () => {
    const draft = {
      ...initialScenario(),
      site: catalog.items[0],
      utcTime: '2027-07-15T00:00',
      latitude: '-89.44',
      longitude: '222.1',
    }
    expect(buildRequest(draft).site).toEqual({ site_id: 'development-site' })
    expect(
      buildRequest({ ...draft, mode: 'custom', name: 'Test' }).site,
    ).toEqual({ name: 'Test', latitude: -89.44, longitude: 222.1 })
    expect(
      buildRequest({ ...draft, mode: 'custom', name: '' }).site,
    ).not.toHaveProperty('site_id')
  })
  it.each([
    ['latitude', '91'],
    ['latitude', '-91'],
    ['latitude', ''],
    ['latitude', 'NaN'],
    ['longitude', '360'],
    ['longitude', '-181'],
    ['height', '21'],
    ['height', '-1'],
    ['margin', '5.1'],
    ['margin', ''],
  ])('rejects invalid %s=%s without clamping', (field, value) => {
    const draft = {
      ...initialScenario(),
      mode: 'custom' as const,
      latitude: '-89',
      longitude: '20',
      utcTime: '2027-07-15T00:00',
      [field]: value,
    }
    expect(() => buildRequest(draft)).toThrow()
    expect(draft[field as keyof typeof draft]).toBe(value)
  })
  it('requires a catalog selection and accepts exact coordinate limits', () => {
    expect(() => buildRequest(initialScenario())).toThrow('Select a catalog')
    expect(
      buildRequest({
        ...initialScenario(),
        mode: 'custom',
        latitude: '-90',
        longitude: '-180',
        utcTime: '2027-07-15T00:00',
        height: '20',
        margin: '5',
      }),
    ).toMatchObject({
      site: { latitude: -90, longitude: -180 },
      observer_height_m: 20,
      visibility_margin_deg: 5,
      horizon_mode: 'geometric',
    })
  })
})
