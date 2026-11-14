import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../../api/client'
import { ApiClientError } from '../../api/errors'
import {
  accepted,
  deferred,
  failed,
  observationResult,
  queued,
  request,
  running,
  succeeded,
} from '../../test/fixtures'
import type { Job, JobAccepted, NowResult } from '../../api/types'
import { useObservation } from './useObservation'

describe('Observation job lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(apiClient, 'submitNow').mockResolvedValue(accepted)
    vi.spyOn(apiClient, 'getJob').mockResolvedValue(succeeded)
    vi.spyOn(apiClient, 'getResult').mockResolvedValue(observationResult)
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })
  const tick = async (ms = 2000) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms)
    })
  }

  it('polls every two seconds through queued and running, then fetches the result once', async () => {
    vi.mocked(apiClient.getJob)
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(succeeded)
    const { result } = renderHook(useObservation)
    await act(async () => {
      await result.current.submit(request)
    })
    expect(result.current.phase).toBe('queued')
    await tick(1999)
    expect(apiClient.getJob).not.toHaveBeenCalled()
    await tick(1)
    expect(result.current.phase).toBe('queued')
    await tick()
    expect(result.current.phase).toBe('running')
    await tick()
    expect(result.current.result).toEqual(observationResult)
    expect(apiClient.getJob).toHaveBeenCalledWith(
      accepted.status_url,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(apiClient.getResult).toHaveBeenCalledWith(
      accepted.result_url,
      expect.any(Object),
    )
    await tick(10000)
    expect(apiClient.getJob).toHaveBeenCalledTimes(3)
    expect(apiClient.getResult).toHaveBeenCalledTimes(1)
  })
  it('stops after a failed job and preserves the structured error', async () => {
    vi.mocked(apiClient.getJob).mockResolvedValue(failed)
    const { result } = renderHook(useObservation)
    await act(async () => {
      await result.current.submit(request)
    })
    await tick()
    expect(result.current.phase).toBe('failed')
    expect(result.current.error).toMatchObject({
      code: 'TERRAIN_UNAVAILABLE',
      details: failed.error!.details,
    })
    await tick(10000)
    expect(apiClient.getJob).toHaveBeenCalledTimes(1)
    expect(apiClient.getResult).not.toHaveBeenCalled()
  })
  it.each(['JOB_EXPIRED', 'JOB_NOT_FOUND', 'NETWORK_ERROR'])(
    'stops on %s while polling',
    async (code) => {
      vi.mocked(apiClient.getJob).mockRejectedValue(
        new ApiClientError({ code, message: code }),
      )
      const { result } = renderHook(useObservation)
      await act(async () => {
        await result.current.submit(request)
      })
      await tick()
      expect(result.current.error?.code).toBe(code)
      expect(result.current.result).toBeNull()
      await tick(10000)
      expect(apiClient.getJob).toHaveBeenCalledTimes(1)
    },
  )
  it('handles terrain validation at submission and expiration during result retrieval', async () => {
    vi.mocked(apiClient.submitNow).mockRejectedValueOnce(
      new ApiClientError({
        code: 'TERRAIN_UNAVAILABLE',
        message: 'Terrain unavailable',
      }),
    )
    const { result } = renderHook(useObservation)
    await act(async () => {
      await result.current.submit(request)
    })
    expect(result.current.error?.code).toBe('TERRAIN_UNAVAILABLE')
    vi.mocked(apiClient.getResult).mockRejectedValueOnce(
      new ApiClientError({ code: 'JOB_EXPIRED', message: 'Expired' }),
    )
    await act(async () => {
      await result.current.submit(request)
    })
    await tick()
    expect(result.current.error?.code).toBe('JOB_EXPIRED')
  })
  it('does not overlap polls and aborts on reset and unmount', async () => {
    const pending = deferred<Job>()
    vi.mocked(apiClient.getJob).mockReturnValue(pending.promise)
    const { result, unmount } = renderHook(useObservation)
    await act(async () => {
      await result.current.submit(request)
    })
    await tick(10000)
    expect(apiClient.getJob).toHaveBeenCalledTimes(1)
    const signal = vi.mocked(apiClient.getJob).mock.calls[0][1]!.signal!
    act(() => result.current.reset())
    expect(signal.aborted).toBe(true)
    await act(async () => {
      pending.resolve(succeeded)
      await pending.promise
    })
    expect(result.current.phase).toBe('idle')
    expect(apiClient.getResult).not.toHaveBeenCalled()
    await act(async () => {
      await result.current.submit(request)
    })
    const submitSignal = vi.mocked(apiClient.submitNow).mock.calls[1][1]!
      .signal!
    unmount()
    expect(submitSignal.aborted).toBe(true)
    await tick(10000)
    expect(apiClient.getJob).toHaveBeenCalledTimes(1)
  })
  it('ignores an old accepted response after a newer request', async () => {
    const old = deferred<JobAccepted>()
    vi.mocked(apiClient.submitNow).mockReturnValueOnce(old.promise)
    const { result } = renderHook(useObservation)
    act(() => {
      void result.current.submit(request)
    })
    await act(async () => {
      await result.current.submit({
        ...request,
        target_time: '2028-01-01T00:00:00Z',
      })
    })
    await act(async () => {
      old.resolve({ ...accepted, job_id: 'late-job' })
      await old.promise
    })
    expect(result.current.jobId).toBe(accepted.job_id)
    await tick()
    expect(result.current.phase).toBe('succeeded')
    expect(apiClient.getJob).toHaveBeenCalledTimes(1)
  })
  it('ignores a late result from A after B succeeds, even if transport ignores abort', async () => {
    const old = deferred<NowResult>()
    vi.mocked(apiClient.getResult)
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce({
        ...observationResult,
        site: { ...observationResult.site, name: 'Scenario B' },
      })
    const { result } = renderHook(useObservation)
    await act(async () => {
      await result.current.submit(request)
    })
    await tick()
    expect(result.current.phase).toBe('loading-result')
    await act(async () => {
      await result.current.submit({
        ...request,
        target_time: '2028-01-01T00:00:00Z',
      })
    })
    await tick()
    expect(result.current.result?.site.name).toBe('Scenario B')
    await act(async () => {
      old.resolve(observationResult)
      await old.promise
    })
    expect(result.current.result?.site.name).toBe('Scenario B')
  })
})
