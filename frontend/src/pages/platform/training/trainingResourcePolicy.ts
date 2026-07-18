import type { TaskType } from '../../../platform/types'

export type CpuTrainingPolicy = {
  defaultBatch: number
  maxBatch: number
  defaultImageSize: number
  maxImageSize: number
}

export function cpuTrainingPolicy(task: TaskType): CpuTrainingPolicy {
  return {
    defaultBatch: task === 'segment' ? 1 : 2,
    maxBatch: task === 'segment' ? 1 : 4,
    defaultImageSize: 320,
    maxImageSize: 640,
  }
}

export function normalizeCpuTrainingValues(
  task: TaskType,
  values: { batch?: number; imageSize?: number },
): { batch: number; imageSize: number } {
  const policy = cpuTrainingPolicy(task)
  return {
    batch: values.batch && values.batch <= policy.maxBatch ? values.batch : policy.defaultBatch,
    imageSize: values.imageSize && values.imageSize <= policy.maxImageSize
      ? values.imageSize
      : policy.defaultImageSize,
  }
}
