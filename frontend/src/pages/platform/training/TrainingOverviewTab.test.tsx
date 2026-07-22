import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import type { TrainingRun } from '../../../platform/types'
import { TrainingOverviewTab } from './TrainingOverviewTab'

const run: TrainingRun = {
  id: 'run-1', name: '分割训练', task: 'segment', status: 'running', phase: 'training',
  progress: 24, epoch: 48, epochs: 200, datasetReleaseId: 'release-1', datasetName: '现场数据',
  baseModel: 'yolo26s-seg.pt', batch: 2, imageSize: 640, device: 'cuda:0', createdAt: '2026-07-22',
  duration: '1小时18分', metrics: { primaryLabel: 'Mask mAP50', primary: 0.42 }, logs: [],
  selectedClasses: ['类别 A', '类别 B'], classAliases: {}, executionMode: 'train', presetId: 'gpu-quality',
  patience: 0, optimizer: 'AdamW', closeMosaic: 15, augmentProfile: 'standard',
  augmentation: { mosaic: 1, mixup: 0, copy_paste: 0, degrees: 0, translate: 0.1, scale: 0.5, fliplr: 0.5, hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4 },
}

const details: TrainingRunDetailsApiResponse = {
  run_id: 'run-1',
  configuration: {
    name: '分割训练', task_type: 'segment', dataset_release_id: 'release-1', base_model: 'yolo26s-seg.pt',
    epochs: 200, batch: 2, image_size: 640, device: 'cuda:0', selected_classes: ['类别 A', '类别 B'],
    class_aliases: {}, preset_id: 'gpu-quality', patience: 0, optimizer: 'AdamW', close_mosaic: 15,
    augment_profile: 'standard',
  },
  timing: { epoch_seconds: 96, eta_seconds: 14592 },
  split_distribution: {
    requested_ratios: { train: 80, val: 10, test: 10 }, actual_ratios: { train: 80, val: 10, test: 10 },
    split_counts: { train: 519, val: 50, test: 70 }, split_seed: 42, grouping_strategy: 'source_group',
  },
  epoch_history: [{
    epoch: 48, map50_mask: 0.42, map50_95_mask: 0.21, map50_box: 0.51, map50_95_box: 0.28,
    train_box_loss: 0.8, train_seg_loss: 1.1, train_cls_loss: 0.3, train_dfl_loss: 0.7,
  }],
  latest_metrics: {}, artifacts: [], logs: [], warnings: [], failure_diagnostic: null,
  recovery_options: null, related_runs: [], dataset_quality: null, test_metrics: null, quality_report: null,
}

describe('TrainingOverviewTab', () => {
  it('explains current progress, quality, losses, dataset roles, and key configuration', () => {
    const html = renderToStaticMarkup(<TrainingOverviewTab run={run} details={details} />)
    expect(html).toContain('当前阶段')
    expect(html).toContain('预计剩余')
    expect(html).toContain('Mask mAP50')
    expect(html).toContain('Mask Loss')
    expect(html).toContain('Class Loss')
    expect(html).toContain('用于更新模型参数')
    expect(html).toContain('最后 15 轮停止 Mosaic')
    expect(html).toContain('类别 A')
  })

  it('explains when validation metrics will appear without fabricating zeroes', () => {
    const empty = { ...details, epoch_history: [] }
    const html = renderToStaticMarkup(<TrainingOverviewTab run={{ ...run, metrics: { primaryLabel: 'Mask mAP50' } }} details={empty} />)
    expect(html).toContain('首轮验证完成后生成')
    expect(html).not.toContain('0.0000')
  })
})
