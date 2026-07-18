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
