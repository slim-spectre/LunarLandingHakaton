import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { apiClient } from './api/client'
import { ApiClientError } from './api/errors'
import {
  accepted,
  catalog,
  observationResult,
  resources,
  succeeded,
} from './test/fixtures'
import type { LunarMapProps } from './features/map'
import type { LunarSceneProps } from './features/scene'

const visual = vi.hoisted(() => ({ map: vi.fn(), scene: vi.fn() }))
vi.mock('./features/map', () => ({
  LunarMap: (props: LunarMapProps) => {
    visual.map(props)
    return (
      <button
        type="button"
        onClick={() =>
          props.onSelectCoordinate?.({ latitude: -88, longitude: 25 })
        }
      >
        Select test map coordinate
      </button>
    )
  },
}))
vi.mock('./features/scene', () => ({
  LunarScene: (props: LunarSceneProps) => {
    visual.scene(props)
    return <div data-testid="scene-integration" />
  },
}))

beforeEach(() => {
  vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
    status: 'healthy',
    service: 'lunar-navigator-api',
    database: 'ok',
    timestamp: '2026-11-14T10:00:00Z',
  })
  vi.spyOn(apiClient, 'getSites').mockResolvedValue(catalog)
  vi.spyOn(apiClient, 'getResources').mockResolvedValue(resources)
  vi.spyOn(apiClient, 'submitNow').mockResolvedValue(accepted)
  vi.spyOn(apiClient, 'getJob').mockResolvedValue(succeeded)
  vi.spyOn(apiClient, 'getResult').mockResolvedValue(observationResult)
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  visual.map.mockClear()
  visual.scene.mockClear()
})

async function selectCatalog() {
  await screen.findByRole('option', { name: 'Synthetic catalog site' })
  fireEvent.change(screen.getByLabelText('Catalog site'), {
    target: { value: 'development-site' },
  })
  fireEvent.change(screen.getByLabelText('Observation date and time (UTC)'), {
    target: { value: '2027-07-15T00:00:00' },
  })
}

describe('Stage 1 observation workspace', () => {
  it('starts with unknown operational values and no fabricated directions', async () => {
    const { container } = render(<App />)
    expect(screen.getByTestId('app-title')).toHaveTextContent(
      'Lunar Landing Site Navigator',
    )
    expect(screen.getByText('Stage 1')).toBeInTheDocument()
    expect(screen.getByText(/Sun visibility: Unknown/)).toBeInTheDocument()
    expect(
      screen.getByText('Simultaneous availability: Unknown'),
    ).toBeInTheDocument()
    expect(visual.scene.mock.lastCall![0]).toMatchObject({
      sunDirectionEnu: null,
      earthDirectionEnu: null,
    })
    expect(container.textContent).not.toMatch(/\d+\s*(%|watts|mbps)/i)
    expect(apiClient.submitNow).not.toHaveBeenCalled()
    await screen.findByText('No matching articles in the available feed.')
  })
  it('submits a catalog ID with an explicit UTC timestamp and source links', async () => {
    render(<App />)
    await selectCatalog()
    expect(
      screen.getByRole('link', { name: /Official site source/ }),
    ).toHaveAttribute('href', catalog.items[0].source_url)
    expect(screen.getByRole('link', { name: /QuickMap/ })).toHaveAttribute(
      'href',
      catalog.items[0].quickmap_url,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Request observation' }))
    await waitFor(() =>
      expect(apiClient.submitNow).toHaveBeenCalledWith(
        {
          site: { site_id: 'development-site' },
          target_time: '2027-07-15T00:00:00Z',
          horizon_mode: 'geometric',
          observer_height_m: 2,
          visibility_margin_deg: 0,
        },
        expect.any(Object),
      ),
    )
    expect(
      await screen.findByText('Queued — waiting for the worker'),
    ).toBeInTheDocument()
  })
  it('submits custom coordinates without a catalog ID and never clamps invalid latitude', async () => {
    render(<App />)
    await selectCatalog()
    fireEvent.click(screen.getByLabelText('Custom coordinates'))
    fireEvent.change(screen.getByLabelText('Latitude (°)'), {
      target: { value: '91' },
    })
    fireEvent.change(screen.getByLabelText('Longitude (° east)'), {
      target: { value: '222.1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Request observation' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Latitude must be -90 to 90',
    )
    expect(screen.getByLabelText('Latitude (°)')).toHaveValue(91)
    expect(apiClient.submitNow).not.toHaveBeenCalled()
    expect(visual.map.mock.lastCall![0].selectedCoordinate).toBeNull()
    fireEvent.change(screen.getByLabelText('Latitude (°)'), {
      target: { value: '-89.44' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Request observation' }))
    await waitFor(() => expect(apiClient.submitNow).toHaveBeenCalled())
    expect(vi.mocked(apiClient.submitNow).mock.calls[0][0].site).toEqual({
      latitude: -89.44,
      longitude: 222.1,
    })
  })
  it('shares map selection with the custom form without transforming coordinates', async () => {
    render(<App />)
    await selectCatalog()
    fireEvent.click(
      screen.getByRole('button', { name: 'Select test map coordinate' }),
    )
    expect(screen.getByLabelText('Custom coordinates')).toBeChecked()
    expect(screen.getByLabelText('Latitude (°)')).toHaveValue(-88)
    expect(screen.getByLabelText('Longitude (° east)')).toHaveValue(25)
    expect(visual.map.mock.lastCall![0]).toMatchObject({
      selectedCoordinate: { latitude: -88, longitude: 25 },
      selectedSiteId: null,
    })
  })
  it('filters and paginates the server catalog', async () => {
    vi.mocked(apiClient.getSites).mockResolvedValue({ ...catalog, total: 51 })
    render(<App />)
    await selectCatalog()
    fireEvent.click(screen.getByRole('button', { name: 'Next sites' }))
    await waitFor(() =>
      expect(apiClient.getSites).toHaveBeenLastCalledWith(
        { limit: 50, offset: 50 },
        expect.any(Object),
      ),
    )
    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: 'apollo' },
    })
    await waitFor(() =>
      expect(apiClient.getSites).toHaveBeenLastCalledWith(
        { category: 'apollo', limit: 50, offset: 0 },
        expect.any(Object),
      ),
    )
    expect(screen.getByLabelText('Catalog site')).toHaveValue('')
  })
  it('displays actual returned values and provenance, integrates ENU vectors, and clears them on edit', async () => {
    vi.mocked(apiClient.getResult).mockResolvedValue({
      ...observationResult,
      meta: { ...observationResult.meta, data_status: 'cached' },
    })
    render(<App />)
    await selectCatalog()
    vi.useFakeTimers()
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: 'Request observation' }),
      )
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(screen.getByText('Observation ready')).toBeInTheDocument()
    const section = screen.getByRole('region', { name: 'Observation' })
    expect(within(section).getByText('cached')).toBeInTheDocument()
    expect(
      within(section).getByText('Synthetic development site'),
    ).toBeInTheDocument()
    expect(
      within(section).getByText(/-89.44° latitude, -137.9° east/),
    ).toBeInTheDocument()
    expect(
      within(section).getByText('2027-07-15T00:00:00Z (UTC)'),
    ).toBeInTheDocument()
    expect(within(section).getAllByRole('cell', { name: '30°' })).toHaveLength(
      2,
    )
    expect(within(section).getAllByRole('cell', { name: 'Yes' })).toHaveLength(
      2,
    )
    expect(
      within(section).getByText('development-fixture-v1'),
    ).toBeInTheDocument()
    expect(
      within(section).getByRole('link', { name: /Synthetic fixture/ }),
    ).toHaveAttribute('href', observationResult.meta.sources[0].url)
    expect(visual.scene.mock.lastCall![0]).toMatchObject({
      sunDirectionEnu: observationResult.point.sun.direction_enu,
      earthDirectionEnu: observationResult.point.earth.direction_enu,
      observerHeightM: 2,
    })
    fireEvent.change(screen.getByLabelText('Observer height (m)'), {
      target: { value: '3' },
    })
    expect(screen.queryByText('Synthetic development site')).toBeNull()
    expect(
      screen.getByText('Simultaneous availability: Unknown'),
    ).toBeInTheDocument()
    expect(visual.scene.mock.lastCall![0]).toMatchObject({
      sunDirectionEnu: null,
      earthDirectionEnu: null,
    })
  })
  it.each([
    'TERRAIN_UNAVAILABLE',
    'JOB_EXPIRED',
    'JOB_NOT_FOUND',
    'NETWORK_ERROR',
  ])('shows %s without a successful fallback', async (code) => {
    vi.mocked(apiClient.submitNow).mockRejectedValue(
      new ApiClientError({ code, message: 'Controlled test failure' }),
    )
    render(<App />)
    await selectCatalog()
    fireEvent.click(screen.getByRole('button', { name: 'Request observation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(code)
    expect(
      screen.getByText('Simultaneous availability: Unknown'),
    ).toBeInTheDocument()
    expect(apiClient.getResult).not.toHaveBeenCalled()
  })
  it('allows custom entry after catalog failure and offers a catalog retry', async () => {
    vi.mocked(apiClient.getSites)
      .mockRejectedValueOnce(
        new ApiClientError({
          code: 'DATABASE_UNAVAILABLE',
          message: 'Catalog unavailable',
        }),
      )
      .mockResolvedValueOnce(catalog)
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Catalog unavailable',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Retry catalog' }))
    await screen.findByRole('option', { name: 'Synthetic catalog site' })
    fireEvent.click(screen.getByLabelText('Custom coordinates'))
    expect(screen.getByLabelText('Latitude (°)')).toBeInTheDocument()
  })
})
