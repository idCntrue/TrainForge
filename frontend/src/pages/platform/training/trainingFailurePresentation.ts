export type RecoveryAction = 'safe_retry' | 'evaluate_best'

export function failedRunPresentation(input: {
  lastSuccessfulEpoch?: number | null
  totalEpochs?: number | null
  latestMetric?: number | null
  canSafeRetry: boolean
  canEvaluateBest: boolean
}) {
  const epoch = input.lastSuccessfulEpoch
  const total = input.totalEpochs
  return {
    progressText: epoch != null && total != null ? `第 ${epoch}/${total} 轮后失败` : '训练未完成',
    metricText: input.latestMetric == null ? '--' : input.latestMetric.toFixed(4),
    actions: [
      ...(input.canSafeRetry ? ['safe_retry' as const] : []),
      ...(input.canEvaluateBest ? ['evaluate_best' as const] : []),
    ],
  }
}
