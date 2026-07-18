import { describe, expect, it } from 'vitest'
import { failedRunPresentation } from './trainingFailurePresentation'

describe('failed run presentation', () => {
  it('uses the last real metric and exposes available recovery actions', () => {
    const view = failedRunPresentation({
      lastSuccessfulEpoch: 78, totalEpochs: 100, latestMetric: undefined,
      canSafeRetry: true, canEvaluateBest: true,
    })
    expect(view.progressText).toBe('第 78/100 轮后失败')
    expect(view.metricText).toBe('--')
    expect(view.actions).toEqual(['safe_retry', 'evaluate_best'])
  })
})
