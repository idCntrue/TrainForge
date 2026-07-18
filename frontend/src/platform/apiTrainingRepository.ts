import type { TrainingApiClient, TrainingRunApiResponse } from '../api'
import type { CreateTrainingRunInput, TrainingRepository, TrainingRun } from './types'

function formatDuration(startValue: string, endValue: string): string {
  const seconds = Math.max(0, Math.floor((Date.parse(endValue) - Date.parse(startValue)) / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  return [hours, minutes, remainder].map((value) => String(value).padStart(2, '0')).join(':')
}

export function mapTrainingRun(run: TrainingRunApiResponse): TrainingRun {
  const epoch = run.epoch ?? 0
  return {
    id: run.id,
    name: run.name,
    task: run.task_type,
    status: run.status,
    phase: run.phase,
    progress: run.progress,
    epoch,
    epochs: run.epochs,
    datasetReleaseId: run.dataset_release_id,
    datasetName: run.dataset_release_id,
    baseModel: run.base_model,
    batch: run.batch,
    imageSize: run.image_size,
    device: run.device,
    createdAt: new Date(run.created_at).toLocaleString('zh-CN', { hour12: false }),
    duration: formatDuration(run.created_at, run.finished_at ?? run.updated_at),
    metrics: {
      primary: run.metrics.mask_map50 ?? run.metrics.map50 ?? undefined,
      primaryLabel: run.task_type === 'segment' ? 'Mask mAP50' : 'mAP50',
      precision: run.metrics.precision ?? undefined,
      recall: run.metrics.recall ?? undefined,
      boxMap: run.metrics.map50 ?? undefined,
      maskMap: run.metrics.mask_map50 ?? undefined,
    },
    logs: [`${run.phase}: ${run.message}`],
    selectedClasses: run.selected_classes,
    classAliases: run.class_aliases,
    sourceRunId: run.source_run_id ?? undefined,
    executionMode: run.execution_mode,
    presetId: run.preset_id,
  }
}

type TrainingRepositoryClient = Pick<TrainingApiClient,
  'listTrainingRuns' | 'getTrainingRun' | 'createTrainingRun' | 'refreshTrainingRun' |
  'cancelTrainingRun' | 'deleteTrainingRun'
>

export function createApiTrainingRepository(client: TrainingRepositoryClient): TrainingRepository {
  return {
    async listTrainingRuns(filters) {
      const runs = (await client.listTrainingRuns()).map(mapTrainingRun)
      return runs.filter((run) => (!filters.task || run.task === filters.task) && (!filters.status || run.status === filters.status))
    },
    async getTrainingRun(id) {
      return mapTrainingRun(await client.getTrainingRun(id))
    },
    async createTrainingRun(input: CreateTrainingRunInput) {
      return mapTrainingRun(await client.createTrainingRun({
        name: input.name,
        task_type: input.task,
        dataset_release_id: input.datasetReleaseId,
        base_model: input.baseModel,
        epochs: input.epochs,
        batch: input.batch,
        image_size: input.imageSize,
        device: input.device,
        selected_classes: input.selectedClasses ?? [],
        class_aliases: input.classAliases ?? {},
        preset_id: input.presetId ?? 'custom',
        augmentation: input.augmentation,
      }))
    },
    async refreshTrainingRun(id) {
      return mapTrainingRun(await client.refreshTrainingRun(id))
    },
    async cancelTrainingRun(id) {
      return mapTrainingRun(await client.cancelTrainingRun(id))
    },
    async deleteTrainingRun(id, deleteArtifacts, cascade = false) {
      if (cascade) await client.deleteTrainingRun(id, deleteArtifacts, true)
      else await client.deleteTrainingRun(id, deleteArtifacts)
    },
  }
}
