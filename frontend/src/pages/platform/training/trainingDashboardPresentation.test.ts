import { describe, expect, it } from 'vitest'
import type { TrainingArtifactApiResponse, TrainingEpochMetrics } from '../../../api'
import {
  artifactGroups,
  filterLogLines,
  defaultMetricMode,
  latestFiniteMetric,
  lossCards,
  lossTrend,
  metricCards,
  resultImageGroups,
  splitPresentation,
} from './trainingDashboardPresentation'

const artifact = (key: string, kind: TrainingArtifactApiResponse['kind'] = 'image'): TrainingArtifactApiResponse => ({
  key,
  kind,
  name: `${key}.${kind === 'weight' ? 'pt' : 'png'}`,
  path: `/runs/demo/${key}`,
  size_bytes: 1024,
})

describe('training dashboard presentation', () => {
  it('returns zero-safe dataset split percentages', () => {
    expect(splitPresentation({ train: 0, val: 0, test: 0 })).toEqual({
      total: 0,
      items: [
        { key: 'train', label: '训练集', count: 0, percent: 0 },
        { key: 'val', label: '验证集', count: 0, percent: 0 },
        { key: 'test', label: '测试集', count: 0, percent: 0 },
      ],
    })
  })

  it('keeps non-empty dataset split percentages equal to 100', () => {
    const result = splitPresentation({ train: 1, val: 1, test: 1 })
    expect(result.items.reduce((sum, item) => sum + item.percent, 0)).toBe(100)
  })

  it('selects the task-appropriate default chart mode', () => {
    expect(defaultMetricMode('segment')).toBe('mask')
    expect(defaultMetricMode('detect')).toBe('box')
  })

  it('keeps zero loss as a valid improving metric', () => {
    const history: TrainingEpochMetrics[] = [
      { epoch: 1, train_seg_loss: 0.4 },
      { epoch: 2, train_seg_loss: 0.2 },
      { epoch: 3, train_seg_loss: 0 },
    ]
    expect(lossTrend(history, 'train_seg_loss')).toMatchObject({ state: 'improving', latest: 0 })
  })

  it('does not claim a trend from one sample and detects worsening loss', () => {
    expect(lossTrend([{ epoch: 1, train_box_loss: 0.3 }], 'train_box_loss').state).toBe('unavailable')
    expect(lossTrend([
      { epoch: 1, train_box_loss: 0.2 },
      { epoch: 2, train_box_loss: 0.25 },
      { epoch: 3, train_box_loss: 0.4 },
    ], 'train_box_loss').state).toBe('worsening')
  })

  it('selects the newest finite metric without fabricating missing values', () => {
    const history: TrainingEpochMetrics[] = [
      { epoch: 1, map50_mask: 0.31 },
      { epoch: 2, map50_mask: Number.NaN },
      { epoch: 3, map50_mask: 0.42 },
    ]
    expect(latestFiniteMetric(history, 'map50_mask')).toBe(0.42)
    expect(latestFiniteMetric(history, 'missing')).toBeNull()
  })

  it('builds task-specific quality and loss cards from real telemetry', () => {
    const history: TrainingEpochMetrics[] = [{
      epoch: 1,
      map50_mask: 0.42,
      map50_95_mask: 0.21,
      map50_box: 0.55,
      map50_95_box: 0.32,
      train_box_loss: 1.1,
      train_seg_loss: 0.9,
      train_cls_loss: 0.4,
      train_dfl_loss: 0.7,
    }]
    expect(metricCards('segment', history).map((item) => item.key)).toEqual([
      'map50_mask', 'map50_95_mask', 'map50_box', 'map50_95_box',
    ])
    expect(metricCards('detect', history).map((item) => item.key)).toEqual([
      'map50_box', 'map50_95_box',
    ])
    expect(lossCards('segment', history).map((item) => item.key)).toEqual([
      'train_box_loss', 'train_seg_loss', 'train_cls_loss', 'train_dfl_loss',
    ])
  })

  it('classifies and filters logs while preserving original line numbers', () => {
    const lines = [
      'Ultralytics training started',
      'Epoch 3/200 GPU_mem 7.2G',
      'WARNING low worker count',
      'Traceback: CUDA out of memory',
    ]
    expect(filterLogLines(lines, { mode: 'diagnostic', level: 'all', query: '' })).toEqual([
      { number: 3, text: lines[2], level: 'warning' },
      { number: 4, text: lines[3], level: 'error' },
    ])
    expect(filterLogLines(lines, { mode: 'live', level: 'epoch', query: 'gpu' })).toEqual([
      { number: 2, text: lines[1], level: 'epoch' },
    ])
  })

  it('groups result images by user purpose', () => {
    const groups = resultImageGroups([
      artifact('val_batch0_pred'),
      artifact('confusion_matrix'),
      artifact('PR_curve'),
      artifact('train_batch0'),
    ])
    expect(groups.predictions.map((item) => item.key)).toEqual(['val_batch0_pred'])
    expect(groups.confusion.map((item) => item.key)).toEqual(['confusion_matrix'])
    expect(groups.curves.map((item) => item.key)).toEqual(['PR_curve'])
    expect(groups.other.map((item) => item.key)).toEqual(['train_batch0'])
  })

  it('promotes best and last weights without hiding other files', () => {
    const groups = artifactGroups([
      artifact('best_pt', 'weight'),
      artifact('last_pt', 'weight'),
      artifact('results_csv', 'file'),
      artifact('runner_log', 'file'),
      artifact('args', 'file'),
    ])
    expect(groups.weights.map((item) => item.key)).toEqual(['best_pt', 'last_pt'])
    expect(groups.reports.map((item) => item.key)).toEqual(['results_csv', 'runner_log'])
    expect(groups.other.map((item) => item.key)).toEqual(['args'])
  })
})
