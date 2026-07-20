import { describe, expect, it } from 'vitest'
import { buildConfirmationRows, describeEarlyStopping, moveWizardStep, trainingCreationSteps } from './trainingCreationWizard'

describe('training creation wizard', () => {
  it('owns fields in four ordered steps', () => {
    expect(trainingCreationSteps.map((step) => step.title)).toEqual(['基础设置', '训练策略', '数据增强', '确认启动'])
    expect(trainingCreationSteps[1].fields).toContain('patience')
    expect(trainingCreationSteps[2].fields).toContain('augmentation')
  })

  it('keeps navigation within the wizard boundaries', () => {
    expect(moveWizardStep(0, -1)).toBe(0)
    expect(moveWizardStep(0, 1)).toBe(1)
    expect(moveWizardStep(3, 1)).toBe(3)
  })

  it('builds a readable confirmation summary', () => {
    const rows = buildConfirmationRows({ name: 'demo', task: 'segment', datasetReleaseId: 'release-1', baseModel: 'yolo11n-seg.pt', epochs: 100, batch: 2, imageSize: 640, device: '0', patience: 20, optimizer: 'AdamW', closeMosaic: 10, augmentProfile: 'standard' })
    expect(rows).toContainEqual({ label: '提前停止耐心值', value: '20 轮' })
    expect(rows).toContainEqual({ label: '优化器', value: 'AdamW' })
  })

  it('explains an early stop using the actual best and completed epochs', () => {
    expect(describeEarlyStopping({ requestedEpochs: 150, completedEpochs: 70, bestEpoch: 49, patience: 20, stoppedEarly: true }))
      .toBe('最佳轮次 49，连续 20 轮未改善，于第 70 轮提前停止。训练正常完成，候选模型使用 best.pt。')
    expect(describeEarlyStopping({ requestedEpochs: 100, completedEpochs: 100, bestEpoch: 88, patience: 20, stoppedEarly: false })).toContain('完成 100 轮')
  })
})
