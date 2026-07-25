export interface AdaptivePollingOptions {
  foregroundMs: number
  backgroundMs: number
  maxRetryMs?: number
  isHidden?: () => boolean
  onError?: (error: unknown) => void
}

export function startAdaptivePolling(
  task: (signal: AbortSignal) => Promise<void>,
  options: AdaptivePollingOptions,
): () => void {
  let stopped = false
  let failures = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  const isHidden = options.isHidden ?? (() => typeof document !== 'undefined' && document.visibilityState === 'hidden')

  const schedule = () => {
    if (stopped) return
    const normalDelay = isHidden() ? options.backgroundMs : options.foregroundMs
    const retryDelay = Math.min(options.maxRetryMs ?? 15000, normalDelay * 2 ** failures)
    timer = globalThis.setTimeout(run, failures ? retryDelay : normalDelay)
  }

  const run = async () => {
    if (stopped) return
    controller = new AbortController()
    try {
      await task(controller.signal)
      failures = 0
    } catch (error) {
      if (!controller.signal.aborted) {
        failures += 1
        options.onError?.(error)
      }
    } finally {
      controller = undefined
      schedule()
    }
  }

  schedule()
  return () => {
    stopped = true
    if (timer !== undefined) globalThis.clearTimeout(timer)
    controller?.abort()
  }
}
