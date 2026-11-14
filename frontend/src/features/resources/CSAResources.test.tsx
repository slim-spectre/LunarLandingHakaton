import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../../api/client'
import { ApiClientError } from '../../api/errors'
import { resources, resourceItem } from '../../test/fixtures'
import { CSAResources } from './CSAResources'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
describe('CSA resource display', () => {
  it('shows a valid empty feed without invented articles', async () => {
    vi.spyOn(apiClient, 'getResources').mockResolvedValue(resources)
    render(<CSAResources />)
    expect(
      await screen.findByText('No matching articles in the available feed.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('fresh')).toBeInTheDocument()
  })
  it.each(['cached', 'stale'] as const)(
    'shows %s state, publication date, source and plain provider text',
    async (data_status) => {
      vi.spyOn(apiClient, 'getResources').mockResolvedValue({
        ...resources,
        data_status,
        items: [
          {
            ...resourceItem,
            summary: '<img src=x onerror=alert(1)>',
            title: '<b>Moon</b>',
          },
        ],
      })
      const { container } = render(<CSAResources />)
      expect(await screen.findByText(data_status)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: '<b>Moon</b>' })).toHaveAttribute(
        'href',
        resourceItem.url,
      )
      expect(
        screen.getByText('<img src=x onerror=alert(1)>'),
      ).toBeInTheDocument()
      expect(container.querySelector('img')).toBeNull()
      expect(screen.getByText('2027-07-14 12:00:00 UTC')).toBeInTheDocument()
      if (data_status === 'stale')
        expect(
          screen.getByText(/Showing previously retrieved/),
        ).toBeInTheDocument()
    },
  )
  it('shows source errors and permits an explicit refresh', async () => {
    vi.spyOn(apiClient, 'getResources')
      .mockRejectedValueOnce(
        new ApiClientError({
          code: 'SOURCE_UNAVAILABLE',
          message: 'CSA unavailable',
        }),
      )
      .mockResolvedValueOnce(resources)
    render(<CSAResources />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'SOURCE_UNAVAILABLE',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Refresh resources' }))
    expect(
      await screen.findByText('No matching articles in the available feed.'),
    ).toBeInTheDocument()
  })
  it('blocks unsafe links and aborts on unmount', async () => {
    const probe = vi
      .spyOn(apiClient, 'getResources')
      .mockResolvedValue({
        ...resources,
        items: [{ ...resourceItem, url: 'javascript:alert(1)' }],
      })
    const { unmount } = render(<CSAResources />)
    await waitFor(() =>
      expect(screen.getByText(resourceItem.title)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('link')).toBeNull()
    const signal = probe.mock.calls[0][0]!.signal!
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
