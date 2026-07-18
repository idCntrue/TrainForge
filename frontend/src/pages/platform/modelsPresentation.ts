import type { TrainingQualityReport } from '../../api'

export function publicationPresentation(verdict: TrainingQualityReport['verdict'] | undefined) {
  const requiresConfirmation = verdict === 'needs_improvement' || verdict === 'insufficient_evidence'
  return {
    requiresConfirmation,
    title: verdict === 'insufficient_evidence' ? '独立测试证据不足，仍要发布吗？' : '模型质量未达到建议线，仍要发布吗？',
    consequence: verdict === 'insufficient_evidence'
      ? '当前测试样本不足，线上表现无法可靠判断。'
      : '该模型在独立测试中的核心指标偏低，可能产生较多漏检或误报。',
  }
}
