import { describe, expect, it } from 'vitest'
import { qualityPresentation } from './trainingQualityPresentation'

describe('quality presentation', () => {
  it('translates insufficient evidence without claiming poor accuracy', () => {
    expect(qualityPresentation({ verdict: 'insufficient_evidence', confidence: 'low' })).toEqual({
      title: '暂不能判断模型质量', tone: 'warning', confidenceLabel: '评估可信度低',
    })
  })

  it('translates ready models', () => {
    expect(qualityPresentation({ verdict: 'ready', confidence: 'high' }).title).toBe('达到建议发布标准')
  })
})
