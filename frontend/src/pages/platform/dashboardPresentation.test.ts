import { describe, expect, it } from 'vitest'
import { releaseFunnel, workflowStages } from './dashboardPresentation'

describe('dashboard presentation', () => {
  it('marks workflow stages from persisted totals', () => {
    expect(workflowStages({ datasetReleases: 2, models: 0, inferenceRuns: 0 })).toEqual([
      { key: 'data', label: '数据准备', state: 'done', detail: '2 个数据集版本' },
      { key: 'model', label: '模型开发', state: 'current', detail: '训练、评估与模型门禁' },
      { key: 'inference', label: '推理验证', state: 'pending', detail: '图片、批量图片与视频验证' },
    ])
  })

  it('calculates a zero-safe release funnel', () => {
    expect(releaseFunnel(0, 0)).toEqual({ total: 0, published: 0, pending: 0, rate: 0 })
    expect(releaseFunnel(5, 2)).toEqual({ total: 5, published: 2, pending: 3, rate: 40 })
  })
})
