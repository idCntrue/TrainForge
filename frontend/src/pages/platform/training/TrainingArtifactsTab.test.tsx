import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import { TrainingArtifactsTab } from './TrainingArtifactsTab'

describe('TrainingArtifactsTab', () => {
  it('keeps the complete log artifact without repeating recent log content', () => {
    const details: TrainingRunDetailsApiResponse = {
      run_id: 'run-1',
      configuration: {
        name: '训练', task_type: 'segment', dataset_release_id: 'release-1', base_model: 'yolo26s-seg.pt',
        epochs: 200, batch: 2, image_size: 640, device: 'cuda:0', selected_classes: ['类别 A'], class_aliases: {}, optimizer: 'AdamW',
        patience: 0, close_mosaic: 15, augment_profile: 'standard',
      },
      timing: { epoch_seconds: 60, eta_seconds: 600 },
      split_distribution: {
        requested_ratios: { train: 80, val: 10, test: 10 }, actual_ratios: { train: 80, val: 10, test: 10 },
        split_counts: { train: 80, val: 10, test: 10 }, split_seed: 42, grouping_strategy: 'source_group',
      },
      epoch_history: [], latest_metrics: {},
      artifacts: [{ key: 'runner_log', name: 'runner.log', kind: 'file', path: '/runs/run-1/runner.log', size_bytes: 1024 }],
      logs: ['Traceback from recent API logs'],
      warnings: [], failure_diagnostic: null, recovery_options: null, related_runs: [], dataset_quality: null,
      test_metrics: null, quality_report: null,
    }
    const html = renderToStaticMarkup(<TrainingArtifactsTab details={details} />)
    expect(html).toContain('完整运行日志')
    expect(html).not.toContain('最近 200 行')
    expect(html).not.toContain('Traceback from recent API logs')
  })
})
