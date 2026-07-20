import type { DashboardSummary, InferenceRunApiResponse, ModelVersionApiResponse, TrainingRunApiResponse } from '../api'
import { mapTrainingRun } from './apiTrainingRepository'
import type { CreateInferenceRunInput, InferenceRun, ModelArtifact, ModelFilters, PlatformRepository } from './types'
import { gateDefinition } from '../pages/platform/modelGateDiagnostics'

export interface PlatformApiClient {
  dashboard(): Promise<DashboardSummary>
  listTrainingRuns(): Promise<TrainingRunApiResponse[]>
  listModelVersions(): Promise<ModelVersionApiResponse[]>
  listInferenceRuns(): Promise<InferenceRunApiResponse[]>
  createInferenceRun(input: { model_version_id: string; mode: 'image' | 'batch' | 'video'; runtime: 'pt' | 'onnx'; sources: string[]; confidence: number }): Promise<InferenceRunApiResponse>
}

function primaryMetric(model: ModelVersionApiResponse): [string, number] {
  const candidates = model.task_type === 'segment'
    ? [['Mask mAP50', model.metrics.mask_map50], ['mAP50', model.metrics.map50]]
    : [['Box mAP50', model.metrics.box_map50], ['mAP50', model.metrics.map50]]
  const found = candidates.find(([, value]) => typeof value === 'number')
  return found ? [found[0] as string, found[1] as number] : ['mAP50', 0]
}

export function mapModel(model: ModelVersionApiResponse): ModelArtifact {
  const [metricLabel, metric] = primaryMetric(model)
  const artifacts = Object.entries(model.artifacts)
  return {
    id: model.id, name: model.name, version: model.version, task: model.task_type, status: model.status,
    datasetReleaseId: model.dataset_release_id, datasetName: model.dataset_release_id, trainingRunId: model.training_run_id,
    primaryMetric: metric, primaryMetricLabel: metricLabel,
    sizeMb: Math.round(artifacts.reduce((sum, [, item]) => sum + (item.size_bytes ?? 0), 0) / 1024 / 1024 * 10) / 10,
    formats: artifacts.map(([format]) => format.toUpperCase()), publishedAt: model.published_at ?? undefined, createdAt: model.created_at,
    baseModel: '-', weightHash: model.artifacts.pt?.sha256 ?? '-', environment: Object.entries(model.environment).map(([key, value]) => `${key} ${value}`).join(', ') || '-',
    gates: Object.entries(model.gates).map(([key, passed]) => {
      const definition = gateDefinition(key)
      return { key, label: definition.label, status: passed ? 'passed' : 'blocked', detail: passed ? '已通过' : '未通过', advisory: definition.advisory }
    }),
    gateReportPath: model.gate_report_path ?? undefined,
    qualityReport: model.quality_report ?? undefined,
  }
}

export function mapInference(run: InferenceRunApiResponse): InferenceRun {
  const media = run.result?.media ?? []
  const items = run.result?.items ?? []
  const results = run.mode === 'video' && items.length
    ? [{ sourceName: run.sources[0], detections: items.reduce((sum, item) => sum + item.detections.length, 0), detectionItems: [], durationMs: items.reduce((sum, item) => sum + (item.speed?.inference ?? 0), 0) / items.length, summary: `${items.length} 帧，${items.reduce((sum, item) => sum + item.detections.length, 0)} 个目标`, mediaPath: media[0] }]
    : items.map((item, index) => ({
      sourceName: item.source,
      detections: item.detections.length,
      detectionItems: item.detections.map((detection) => ({
        classId: detection.class_id,
        className: detection.class_name,
        confidence: detection.confidence,
        box: detection.box,
        polygon: detection.polygon,
      })),
      durationMs: item.speed?.inference ?? 0,
      summary: `${item.detections.length} 个目标`,
      mediaPath: item.media_path ?? media[index],
    }))
  return {
    id: run.id, mode: run.mode, task: 'detect', modelId: run.model_version_id, runtime: run.runtime, status: run.status,
    confidence: run.confidence, createdAt: run.created_at,
    results,
  }
}

export function createApiPlatformRepository(client: PlatformApiClient): Pick<PlatformRepository, 'getDashboard' | 'listModels' | 'getModel' | 'createInferenceRun'> {
  async function models(filters: ModelFilters = {}) {
    return (await client.listModelVersions()).map(mapModel).filter((model) => (!filters.task || model.task === filters.task) && (!filters.status || model.status === filters.status))
  }
  return {
    async getDashboard() {
      const [summary, backendRuns, backendModels, inferenceRuns] = await Promise.all([client.dashboard(), client.listTrainingRuns(), client.listModelVersions(), client.listInferenceRuns()])
      const runs = backendRuns.map(mapTrainingRun)
      const mappedModels = backendModels.map(mapModel)
      return { totals: { tasks: summary.tasks, dataSources: summary.video_collections + summary.frame_batches, datasetReleases: summary.dataset_releases, trainingRuns: runs.length, models: mappedModels.length, publishedModels: mappedModels.filter((model) => model.status === 'published').length, inferenceRuns: inferenceRuns.length }, activeRun: runs.find((run) => ['running', 'evaluating', 'exporting', 'verifying'].includes(run.status)), recentRuns: runs.slice(0, 4), recentModels: mappedModels.slice(0, 4) }
    },
    listModels: models,
    async getModel(id: string) { return (await models()).find((model) => model.id === id) },
    async createInferenceRun(input: CreateInferenceRunInput) {
      const mapped = mapInference(await client.createInferenceRun({ model_version_id: input.modelId, mode: input.mode, runtime: input.runtime, sources: input.sourceNames, confidence: input.confidence }))
      return { ...mapped, task: input.task }
    },
  }
}
