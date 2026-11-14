import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { LunarMap } from './LunarMap'

describe('LunarMap component', () => {
  it('renders without crashing and shows awaiting coordinate selection by default', () => {
    render(<LunarMap />)
    expect(screen.getByTestId('lunar-map-container')).toBeInTheDocument()
    expect(screen.getByText(/Awaiting coordinate selection/i)).toBeInTheDocument()
    expect(screen.queryByTestId('lunar-coordinate-marker')).not.toBeInTheDocument()
  })

  it('renders selected coordinate marker and updates status bar', () => {
    render(
      <LunarMap
        selectedCoordinate={{ latitude: -89.44, longitude: 222.1 }}
        selectedSiteId="shackleton-connecting-ridge"
      />
    )
    expect(screen.getByTestId('lunar-coordinate-marker')).toBeInTheDocument()
    expect(screen.getByText(/Site: shackleton-connecting-ridge/i)).toBeInTheDocument()
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
      />
    )

    expect(screen.getByTestId('lunar-map-unavailable')).toBeInTheDocument()
    expect(screen.getByText(/DEM coverage unavailable/i)).toBeInTheDocument()

    const viewport = screen.getByTestId('lunar-map-viewport')
    fireEvent.click(viewport, { clientX: 100, clientY: 100 })
    expect(handleSelect).not.toHaveBeenCalled()
  })
})
