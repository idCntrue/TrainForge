import type { CreateTrainingRunInput } from '../../../platform/types'

export const trainingCreationSteps = [
  { title: '基础设置', fields: ['name', 'task', 'datasetReleaseId', 'baseModel', 'device', 'selectedClasses', 'classAliases'] },
  { title: '训练策略', fields: ['presetId', 'epochs', 'batch', 'imageSize', 'patience', 'optimizer', 'closeMosaic'] },
  { title: '数据增强', fields: ['augmentProfile', 'augmentation'] },
  { title: '确认启动', fields: [] },
] as const

export function moveWizardStep(current: number, delta: number): number {
  return Math.max(0, Math.min(trainingCreationSteps.length - 1, current + delta))
}

export function buildConfirmationRows(input: Partial<CreateTrainingRunInput>) {
  return [
    { label: '训练名称', value: input.name || '未填写' },
    { label: '任务 / 数据集', value: `${input.task || '-'} / ${input.datasetReleaseId || '-'}` },
    { label: '基础模型', value: input.baseModel || '未选择' },
    { label: '轮次 / Batch / 分辨率', value: `${input.epochs ?? '-'} / ${input.batch ?? '-'} / ${input.imageSize ?? '-'}` },
    { label: '设备', value: input.device || 'cpu' },
    { label: '提前停止耐心值', value: input.patience === 0 ? '已关闭' : `${input.patience ?? '-'} 轮` },
    { label: '优化器', value: input.optimizer || 'auto' },
    { label: '关闭 Mosaic', value: `${input.closeMosaic ?? '-'} 轮` },
  ]
}

export function describeEarlyStopping(input: { requestedEpochs: number; completedEpochs: number; bestEpoch: number | null; patience: number; stoppedEarly: boolean }): string {
  if (input.stoppedEarly && input.bestEpoch !== null) {
    return `最佳轮次 ${input.bestEpoch}，连续 ${input.patience} 轮未改善，于第 ${input.completedEpochs} 轮提前停止。训练正常完成，候选模型使用 best.pt。`
  }
  return `已完成 ${input.completedEpochs} 轮（计划 ${input.requestedEpochs} 轮），候选模型使用 best.pt。`
}
