import { describe, expect, it } from 'vitest'

import { artifactLabel, epochProgressText, formatDuration, metricText, timingText } from './trainingDetails'

describe('training detail presentation', () => {
  it('formats timing and missing metrics explicitly', () => {
    expect(formatDuration(125)).toBe('2分 5秒')
    expect(formatDuration(null)).toBe('计算中')
    expect(metricText(undefined)).toBe('待生成')
    expect(metricText(0.45678)).toBe('0.4568')
  })

  it('uses clear artifact labels', () => {
    expect(artifactLabel('best_pt')).toBe('最佳权重 best.pt')
    expect(artifactLabel('confusion_matrix')).toBe('混淆矩阵')
  })

  it('does not show completed early-stopped runs as still calculating', () => {
    expect(epochProgressText('completed', 74, 150)).toBe('74 / 150（已提前停止）')
    expect(timingText('completed', null, 'epoch')).toBe('--')
    expect(timingText('completed', null, 'eta')).toBe('已完成')
  })

  it('only shows calculating timing for active runs', () => {
    expect(timingText('running', null, 'epoch')).toBe('计算中')
    expect(timingText('failed', null, 'eta')).toBe('已结束')
  })
})
