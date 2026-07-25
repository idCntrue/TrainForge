import { afterEach, describe, expect, it, vi } from 'vitest'

import { startAdaptivePolling } from './polling'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((next) => { resolve = next })
  return { promise, resolve }
}

describe('startAdaptivePolling', () => {
  afterEach(() => vi.useRealTimers())

  it('waits for the active request before scheduling another poll', async () => {
    vi.useFakeTimers()
    const first = deferred()
    const task = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined)
    const stop = startAdaptivePolling(task, { foregroundMs: 2000, backgroundMs: 15000 })

    await vi.advanceTimersByTimeAsync(2000)
    expect(task).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10000)
    expect(task).toHaveBeenCalledTimes(1)
    first.resolve()
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(1999)
    expect(task).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(task).toHaveBeenCalledTimes(2)
    stop()
  })

  it('aborts the active request when polling stops', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    const task = vi.fn((nextSignal: AbortSignal) => {
      signal = nextSignal
      return new Promise<void>(() => undefined)
    })
    const stop = startAdaptivePolling(task, { foregroundMs: 100, backgroundMs: 1000 })

    await vi.advanceTimersByTimeAsync(100)
    stop()

    expect(signal?.aborted).toBe(true)
  })

  it('uses the background interval while the page is hidden', async () => {
    vi.useFakeTimers()
    const task = vi.fn().mockResolvedValue(undefined)
    const stop = startAdaptivePolling(task, {
      foregroundMs: 2000,
      backgroundMs: 15000,
      isHidden: () => true,
    })

    await vi.advanceTimersByTimeAsync(14999)
    expect(task).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(task).toHaveBeenCalledTimes(1)
    stop()
  })
})
