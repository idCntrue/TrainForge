export type QualityVerdict = 'insufficient_evidence' | 'needs_improvement' | 'trial' | 'ready'

const titles: Record<QualityVerdict, string> = {
  insufficient_evidence: '暂不能判断模型质量',
  needs_improvement: '模型质量需要改进',
  trial: '可进入小范围试用',
  ready: '达到建议发布标准',
}

export function qualityPresentation(input: { verdict: QualityVerdict; confidence: 'low' | 'medium' | 'high' }) {
  return {
    title: titles[input.verdict],
    tone: input.verdict === 'ready' ? 'success' as const : input.verdict === 'needs_improvement' ? 'error' as const : 'warning' as const,
    confidenceLabel: `评估可信度${input.confidence === 'high' ? '高' : input.confidence === 'medium' ? '中' : '低'}`,
  }
}
