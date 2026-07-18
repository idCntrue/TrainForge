import { describe, expect, it } from 'vitest'

import { phaseLabel, statusLabel } from './statusPresentation'

describe('workflow status presentation', () => {
  it('translates persisted statuses without changing their values', () => {
    expect(statusLabel('queued')).toBe('排队中')
    expect(statusLabel('evaluating')).toBe('正在评估')
    expect(statusLabel('interrupted')).toBe('已中断')
  })

  it('explains training phases in user-facing language', () => {
    expect(phaseLabel('preparing')).toBe('正在准备训练资源')
    expect(phaseLabel('test_evaluation')).toBe('正在使用测试集评估最佳权重')
    expect(phaseLabel('artifacts')).toBe('正在整理训练产物')
  })

  it('keeps unknown values visible for diagnostics', () => {
    expect(statusLabel('custom-state')).toBe('custom-state')
    expect(phaseLabel('custom-phase')).toBe('custom-phase')
  })
})
