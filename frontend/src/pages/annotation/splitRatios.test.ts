import { describe, expect, it } from 'vitest'

import { previewSplitCounts, validateSplitRatios } from './splitRatios'

describe('dataset split ratios', () => {
  it('validates a 100 percent allocation', () => {
    expect(validateSplitRatios({ train: 70, val: 20, test: 10 })).toBeUndefined()
    expect(validateSplitRatios({ train: 80, val: 10, test: 0 })).toBe('训练集、验证集和测试集比例必须合计 100%')
  })

  it('previews integer sample counts without losing samples', () => {
    expect(previewSplitCounts(10, { train: 70, val: 20, test: 10 })).toEqual({ train: 7, val: 2, test: 1 })
    expect(Object.values(previewSplitCounts(7, { train: 70, val: 20, test: 10 })).reduce((sum, value) => sum + value, 0)).toBe(7)
  })
})
