import { describe, expect, it, vi } from 'vitest'

import { createApiPlatformRepository } from './apiPlatformRepository'

const model = {
  id: 'model-001', name: 'Example Segment', version: '0.1.0', task_type: 'segment', training_run_id: 'training-001',
  dataset_release_id: 'dataset-001', selected_classes: ['door'], class_aliases: {}, metrics: { mask_map50: 0.42 }, status: 'published',
  gates: { training: true, pt: true, onnx: true, consistency: true },
  artifacts: { pt: { path: 'best.pt', sha256: 'abc', size_bytes: 5_000_000, exists: true }, onnx: { path: 'best.onnx', sha256: 'def', size_bytes: 10_000_000, exists: true } },
  environment: { ultralytics: '8.4.94' }, gate_report_path: 'report.json', created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z', published_at: '2026-07-14T00:01:00Z', archived_at: null,
}

const inference = {
  id: 'inference-001', model_version_id: 'model-001', imported_model_id: null, mode: 'image', runtime: 'pt', sources: ['D:\\managed\\input.jpg'], confidence: 0.25,
  status: 'completed', progress: 100, message: 'Completed', output_directory: 'outputs', result_path: 'result.json',
  result: { items: [{ source: 'image0.jpg', detections: [{ class_id: 0, class_name: 'door', confidence: 0.92, box: [10, 20, 30, 40], polygon: [0.1, 0.2, 0.3, 0.2, 0.3, 0.4] }], speed: { inference: 12.5 } }], media: ['annotated.jpg'] },
  created_at: '2026-07-14T00:02:00Z', updated_at: '2026-07-14T00:02:01Z', finished_at: '2026-07-14T00:02:01Z',
}

function client() {
  return {
    dashboard: vi.fn().mockResolvedValue({ tasks: 2, video_collections: 3, frame_batches: 4, dataset_releases: 1 }),
    listTrainingRuns: vi.fn().mockResolvedValue([]),
    listModelVersions: vi.fn().mockResolvedValue([model]),
    listInferenceRuns: vi.fn().mockResolvedValue([inference]),
    createInferenceRun: vi.fn().mockResolvedValue(inference),
  }
}

describe('API platform repository', () => {
  it('builds dashboard totals from real model and inference resources', async () => {
    const repository = createApiPlatformRepository(client())
    const dashboard = await repository.getDashboard()
    expect(dashboard.gpu).toBeUndefined()
    expect(dashboard.totals).toEqual({ tasks: 2, dataSources: 7, datasetReleases: 1, trainingRuns: 0, models: 1, publishedModels: 1, inferenceRuns: 1 })
    expect(dashboard.recentModels[0].id).toBe('model-001')
  })

  it('maps published model artifacts, gates and metrics', async () => {
    const repository = createApiPlatformRepository(client())
    const models = await repository.listModels({ task: 'segment', status: 'published' })
    expect(models[0]).toMatchObject({ id: 'model-001', task: 'segment', formats: ['PT', 'ONNX'], weightHash: 'abc', primaryMetric: 0.42 })
    expect(models[0].gateReportPath).toBe('report.json')
    expect(models[0].artifacts.pt).toMatchObject({ path: 'best.pt', exists: true })
    expect(models[0].gates.find((gate) => gate.key === 'consistency')).toMatchObject({ label: 'PT 与 ONNX 推理一致性', advisory: false })
    expect(models[0].gates.every((gate) => gate.status === 'passed')).toBe(true)
  })

  it('submits inference runtime and source paths and maps results', async () => {
    const apiClient = client()
    const repository = createApiPlatformRepository(apiClient)
    const run = await repository.createInferenceRun({ mode: 'image', task: 'segment', modelId: 'model-001', runtime: 'pt', confidence: 0.25, sourceNames: ['input.jpg'] })
    expect(apiClient.createInferenceRun).toHaveBeenCalledWith({ model_version_id: 'model-001', mode: 'image', runtime: 'pt', sources: ['input.jpg'], confidence: 0.25 })
    expect(run.results[0]).toMatchObject({ sourceName: 'D:\\managed\\input.jpg', detections: 1, durationMs: 12.5, mediaPath: 'annotated.jpg' })
    expect(run.results[0].detectionItems[0]).toEqual({
      classId: 0,
      className: 'door',
      confidence: 0.92,
      box: [10, 20, 30, 40],
      polygon: [0.1, 0.2, 0.3, 0.2, 0.3, 0.4],
    })
  })
})
