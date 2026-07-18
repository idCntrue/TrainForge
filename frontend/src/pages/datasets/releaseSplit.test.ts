import { describe, expect, it } from 'vitest'

import { formatReleaseSplit } from './releaseSplit'

describe('formatReleaseSplit', () => {
  it('shows actual split counts and requested percentages', () => {
    expect(formatReleaseSplit({
      requested_ratios: { train: 70, val: 20, test: 10 },
      actual_ratios: { train: 68, val: 21, test: 11 },
      split_counts: { train: 68, val: 21, test: 11 },
    })).toBe('训练 68 (70%) / 验证 21 (20%) / 测试 11 (10%)')
  })

  it('marks legacy releases without split metadata', () => {
    expect(formatReleaseSplit({
      requested_ratios: null,
      actual_ratios: {},
      split_counts: {},
    })).toBe('历史版本未记录')
  })

  it('omits zero-percent splits', () => {
    expect(formatReleaseSplit({
      requested_ratios: { train: 80, val: 20, test: 0 },
      actual_ratios: { train: 80, val: 20 },
      split_counts: { train: 8, val: 2 },
    })).toBe('训练 8 (80%) / 验证 2 (20%)')
  })
})
