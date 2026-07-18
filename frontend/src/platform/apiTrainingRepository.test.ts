import { describe, expect, it, vi } from 'vitest'

import { createApiTrainingRepository } from './apiTrainingRepository'

const backendRun = {
  id: 'training-001',
  name: 'Lights baseline',
  task_type: 'detect' as const,
  dataset_release_id: 'dataset-lights-1.0.0',
  base_model: 'yolo11n.pt',
  epochs: 20,
  batch: 4,
  image_size: 640,
  device: 'cuda:0',
  status: 'running' as const,
  progress: 25,
  phase: 'training',
  message: 'Epoch simulation in progress',
  pid: 1234,
  run_directory: 'storage/training-runs/training-001',
  created_at: '2026-07-14T10:00:00Z',
  updated_at: '2026-07-14T10:01:30Z',
  finished_at: null,
  exit_code: null,
  epoch: 5,
  total_epochs: 20,
  metrics: { map50: 0.72, precision: 0.8 },
  artifacts: { best_pt: null, last_pt: null },
  selected_classes: ['light'],
  class_aliases: {},
}

describe('API training repository', () => {
  it('maps backend runs and filters them locally', async () => {
    const client = {
      listTrainingRuns: vi.fn().mockResolvedValue([backendRun]),
      getTrainingRun: vi.fn(),
      createTrainingRun: vi.fn(),
      cancelTrainingRun: vi.fn(),
      deleteTrainingRun: vi.fn(),
      refreshTrainingRun: vi.fn(),
    }
    const repository = createApiTrainingRepository(client)

    const runs = await repository.listTrainingRuns({ task: 'detect', status: 'running' })

    expect(runs).toHaveLength(1)
    expect(runs[0]).toMatchObject({
      id: 'training-001',
      task: 'detect',
      datasetReleaseId: 'dataset-lights-1.0.0',
      epoch: 5,
      duration: '00:01:30',
      logs: ['training: Epoch simulation in progress'],
      metrics: { primary: 0.72, primaryLabel: 'mAP50', precision: 0.8 },
      selectedClasses: ['light'],
    })
  })

  it('returns the mapped cancelled run', async () => {
    const client = {
      listTrainingRuns: vi.fn(),
      getTrainingRun: vi.fn(),
      createTrainingRun: vi.fn(),
      refreshTrainingRun: vi.fn(),
      cancelTrainingRun: vi.fn().mockResolvedValue({
        ...backendRun,
        status: 'cancelled',
        message: 'Cancellation requested',
        finished_at: '2026-07-14T10:02:00Z',
      }),
      deleteTrainingRun: vi.fn(),
    }
    const repository = createApiTrainingRepository(client)

    const cancelled = await repository.cancelTrainingRun('training-001')

    expect(client.cancelTrainingRun).toHaveBeenCalledWith('training-001')
    expect(cancelled.status).toBe('cancelled')
    expect(cancelled.logs).toEqual(['training: Cancellation requested'])
  })

  it('submits custom augmentation controls', async () => {
    const client = {
      listTrainingRuns: vi.fn(), getTrainingRun: vi.fn(), refreshTrainingRun: vi.fn(), cancelTrainingRun: vi.fn(), deleteTrainingRun: vi.fn(),
      createTrainingRun: vi.fn().mockResolvedValue({ ...backendRun, augmentation: { mosaic: 0.8 } }),
    }
    const repository = createApiTrainingRepository(client)

    await repository.createTrainingRun({
      name: 'custom', task: 'detect', datasetReleaseId: 'release-1', baseModel: 'yolo11n.pt',
      epochs: 100, batch: 2, imageSize: 640, device: 'cpu', presetId: 'custom',
      augmentation: { mosaic: 0.8, mixup: 0.1 },
    })

    expect(client.createTrainingRun).toHaveBeenCalledWith(expect.objectContaining({
      preset_id: 'custom',
      augmentation: { mosaic: 0.8, mixup: 0.1 },
    }))
  })

  it('deletes a terminal run with explicit artifact policy', async () => {
    const client = {
      listTrainingRuns: vi.fn(), getTrainingRun: vi.fn(), createTrainingRun: vi.fn(), refreshTrainingRun: vi.fn(), cancelTrainingRun: vi.fn(),
      deleteTrainingRun: vi.fn().mockResolvedValue(undefined),
    }
    const repository = createApiTrainingRepository(client)

    await repository.deleteTrainingRun('training-001', true)

    expect(client.deleteTrainingRun).toHaveBeenCalledWith('training-001', true)
  })
})
