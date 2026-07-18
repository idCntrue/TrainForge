import { describe, expect, it } from 'vitest'

import { reviewStatusLabel } from './reviewStatusPresentation'

describe('review status labels', () => {
  it('translates active review states', () => {
    expect(reviewStatusLabel('selected')).toBe('已保留')
    expect(reviewStatusLabel('candidate')).toBe('待筛选')
    expect(reviewStatusLabel('duplicate')).toBe('重复帧')
  })

  it('translates rejection reasons', () => {
    expect(reviewStatusLabel('rejected/blur')).toBe('模糊')
    expect(reviewStatusLabel('rejected/no-target')).toBe('无目标')
    expect(reviewStatusLabel('rejected/privacy')).toBe('隐私风险')
    expect(reviewStatusLabel('rejected/other')).toBe('其他原因')
  })

  it('keeps unknown backend states visible', () => {
    expect(reviewStatusLabel('rejected/custom')).toBe('custom')
  })
})
