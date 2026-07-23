import type { InferenceMode, TaskType } from '../../platform/types'

export interface InferenceModelOption {
  id: string
  task: TaskType
}

export function selectInitialInferenceModel(
  models: InferenceModelOption[],
  preferredTask: TaskType,
): { task: TaskType; modelId: string | undefined } {
  const selected = models.find((model) => model.task === preferredTask) ?? models[0]
  return {
    task: selected?.task ?? preferredTask,
    modelId: selected?.id,
  }
}

export function selectModelForTask(models: InferenceModelOption[], task: TaskType) {
  return models.find((model) => model.task === task)?.id
}

export function getInferencePreviewKind(
  mode: InferenceMode,
  mediaPath: string | undefined,
): 'image' | 'video' | 'none' {
  if (!mediaPath) return 'none'
  return mode === 'video' ? 'video' : 'image'
}

export function clampInferenceResultIndex(index: number, resultCount: number) {
  if (resultCount <= 0) return 0
  return Math.min(Math.max(index, 0), resultCount - 1)
}

export function canNavigateInferenceResults(mode: InferenceMode, resultCount: number) {
  return mode === 'batch' && resultCount > 1
}
