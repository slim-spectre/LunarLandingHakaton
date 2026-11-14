import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { LunarMap } from './LunarMap'
import { VERIFIED_MAP_LAYERS } from './layers'

describe('LunarMap component', () => {
  it('assembles both verified matrix-zero tiles in a shared geographic surface', () => {
    render(<LunarMap selectedCoordinate={{ latitude: 45, longitude: -90 }} />)
    const images = screen.getAllByTestId('lunar-layer-image')
    expect(images).toHaveLength(2)
    expect(images[0]).toHaveAttribute(
      'href',
      expect.stringContaining('/tiles/0/0/0'),
    )
    expect(images[1]).toHaveAttribute(
      'href',
      expect.stringContaining('/tiles/0/0/1'),
    )
    expect(images[0]).toHaveAttribute('x', '0')
    expect(images[1]).toHaveAttribute('x', '180')
    expect(images[1]).toHaveAttribute('width', '180')
    expect(screen.getByTestId('lunar-coordinate-marker')).toHaveAttribute(
      'cx',
      '90',
    )
    expect(screen.getByTestId('lunar-coordinate-marker')).toHaveAttribute(
      'cy',
      '45',
    )
  })

  it('accounts for image letterboxing and rejects clicks in the margins', () => {
    const select = vi.fn()
    render(<LunarMap onSelectCoordinate={select} />)
    const viewport = screen.getByTestId('lunar-map-viewport')
    vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({
      left: 10,
      top: 20,
      width: 400,
      height: 400,
    } as DOMRect)
    fireEvent.click(viewport, { clientX: 110, clientY: 70 })
    expect(select).not.toHaveBeenCalled()
    fireEvent.click(viewport, { clientX: 110, clientY: 170 })
    expect(select).toHaveBeenCalledWith({ latitude: 45, longitude: -90 })
  })

  it('requests and positions a regional WMS image using its actual extent', () => {
    render(
      <LunarMap
        layers={[{ ...VERIFIED_MAP_LAYERS[1], extent: [-10, -90, 10, -80] }]}
      />,
    )
    const image = screen.getByTestId('lunar-layer-image')
    expect(image).toHaveAttribute(
      'href',
      expect.stringContaining('bbox=-10,-90,10,-80'),
    )
    expect(image).toHaveAttribute('x', '170')
    expect(image).toHaveAttribute('y', '170')
    expect(image).toHaveAttribute('width', '20')
    expect(image).toHaveAttribute('height', '10')
  })
  it('renders without crashing and shows awaiting coordinate selection by default', () => {
    render(<LunarMap />)
    expect(screen.getByTestId('lunar-map-container')).toBeInTheDocument()
    expect(screen.getByText(/Awaiting selection/i)).toBeInTheDocument()
    expect(
      screen.queryByTestId('lunar-coordinate-marker'),
    ).not.toBeInTheDocument()
  })

  it('renders selected coordinate marker and updates status bar', () => {
    render(
      <LunarMap
        selectedCoordinate={{ latitude: -89.44, longitude: 222.1 }}
        selectedSiteId="shackleton-connecting-ridge"
      />,
    )
    expect(screen.getByTestId('lunar-coordinate-marker')).toBeInTheDocument()
    expect(
      screen.getByText(/Site: shackleton-connecting-ridge/i),
    ).toBeInTheDocument()
  })

  it('invokes onSelectCoordinate callback with normalized longitude when clicked', () => {
    const handleSelect = vi.fn()
    render(<LunarMap onSelectCoordinate={handleSelect} />)

    const viewport = screen.getByTestId('lunar-map-viewport')
    // Mock getBoundingClientRect
    vi.spyOn(viewport, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 400,
      height: 200,
      right: 400,
      bottom: 200,
      x: 0,
      y: 0,
      toJSON: () => {},
    })

    // Click at center (x: 200, y: 100) -> latitude: 0, longitude: 0
    fireEvent.click(viewport, { clientX: 200, clientY: 100 })
    expect(handleSelect).toHaveBeenCalledTimes(1)
    const firstCall = handleSelect.mock.calls[0][0]
    expect(firstCall.latitude).toBeCloseTo(0, 1)
    expect(firstCall.longitude).toBeCloseTo(0, 1)

    // Click near bottom (South pole: y: 200 -> lat: -90)
    fireEvent.click(viewport, { clientX: 200, clientY: 200 })
    const secondCall = handleSelect.mock.calls[1][0]
    expect(secondCall.latitude).toBeCloseTo(-90, 1)
  })

  it('renders loading overlay when isLoading is true', () => {
    render(<LunarMap isLoading={true} />)
    expect(screen.getByTestId('lunar-map-loading')).toBeInTheDocument()
    expect(screen.getByText(/Loading lunar map layer/i)).toBeInTheDocument()
  })

  it('renders unavailable state and reason when isUnavailable is true and blocks clicks', () => {
    const handleSelect = vi.fn()
    render(
      <LunarMap
        isUnavailable={true}
        unavailableReason="DEM coverage unavailable at requested resolution"
        onSelectCoordinate={handleSelect}
      />,
    )

    expect(screen.getByTestId('lunar-map-unavailable')).toBeInTheDocument()
    expect(screen.getByText(/DEM coverage unavailable/i)).toBeInTheDocument()

    const viewport = screen.getByTestId('lunar-map-viewport')
    fireEvent.click(viewport, { clientX: 100, clientY: 100 })
    expect(handleSelect).not.toHaveBeenCalled()
  })

  it('supports map layer switching between Moon Trek WMTS and LROC WMS', () => {
    const handleLayerChange = vi.fn()
    render(<LunarMap onLayerChange={handleLayerChange} />)

    const select = screen.getByTestId('map-layer-select') as HTMLSelectElement
    expect(select.value).toBe(VERIFIED_MAP_LAYERS[0].id)

    // Initial layer is Moon Trek WMTS with its advertised lunar CRS
    expect(
      screen.getByText(/urn:ogc:def:crs:EPSG::104903/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        /NASA\/GSFC\/ASU LROC Team; tiles served by NASA\/JPL Moon Trek/i,
      ),
    ).toBeInTheDocument()

    // Switch to LROC WMS layer
    fireEvent.change(select, { target: { value: 'luna_wac_roi_south_summer' } })
    expect(handleLayerChange).toHaveBeenCalledWith('luna_wac_roi_south_summer')
    expect(screen.getByText(/IAU2000:30100/i)).toBeInTheDocument()
    expect(
      screen.getByText(/cite Speyerer and Robinson \(2013\)/i),
    ).toBeInTheDocument()
  })

  it('displays verified QuickMap link without inventing query parameters', () => {
    const verifiedQuickmapUrl =
      'https://quickmap.lroc.asu.edu/?extent=-89.5,221,-89.3,223'
    render(<LunarMap quickmapUrl={verifiedQuickmapUrl} />)

    const link = screen.getByTestId('quickmap-link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', verifiedQuickmapUrl)
    expect(link).toHaveTextContent(/View in QuickMap/i)
  })

  it('detects when selected coordinate is outside layer extent', () => {
    // Custom layer with limited extent
    const regionalLayer = {
      ...VERIFIED_MAP_LAYERS[1],
      id: 'custom_polar_layer',
      extent: [-180, -90, 180, -80], // only south pole below -80 deg
    }

    const { rerender } = render(
      <LunarMap
        layers={[regionalLayer]}
        selectedCoordinate={{ latitude: -85.0, longitude: 0.0 }} // inside extent
      />,
    )
    expect(
      screen.queryByTestId('layer-outside-coverage-banner'),
    ).not.toBeInTheDocument()

    // Move to equator (outside extent)
    rerender(
      <LunarMap
        layers={[regionalLayer]}
        selectedCoordinate={{ latitude: 0.0, longitude: 0.0 }} // outside extent
      />,
    )
    expect(
      screen.getByTestId('layer-outside-coverage-banner'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Location outside layer coverage/i),
    ).toBeInTheDocument()
  })

  it('handles layer image load errors and displays provider error notice', () => {
    const select = vi.fn()
    render(<LunarMap onSelectCoordinate={select} />)
    const img = screen.getAllByTestId('lunar-layer-image')[0]
    expect(img).toBeInTheDocument()

    // Simulate provider 502/503 network failure
    fireEvent.error(img)

    expect(screen.getByTestId('layer-image-error-notice')).toBeInTheDocument()
    expect(
      screen.getByText(/Layer imagery unavailable from provider/i),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry imagery' }))
    expect(select).not.toHaveBeenCalled()
    expect(screen.getAllByTestId('lunar-layer-image')).toHaveLength(2)
  })
})
