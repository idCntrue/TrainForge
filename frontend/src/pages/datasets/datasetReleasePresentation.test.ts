import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import type { DatasetReleaseSummary } from '../../api'
import { formatDatasetReleaseLabel, resolveDatasetReleaseLabel } from './datasetReleasePresentation'

const release = {
  id: 'dataset-otis-inspection-segmentation-0.1.3',
  task_id: 'otis-inspection-segmentation',
  annotation_export_id: 'annotation-1',
  display_name: '电梯标识分割数据集',
  version: '0.1.3',
  status: 'published',
  release_path: 'dataset-releases/otis/dataset-v0.1.3',
  created_at: '2026-07-16T00:00:00Z',
  requested_ratios: null,
  actual_ratios: {},
  split_counts: {},
  split_seed: null,
  grouping_strategy: null,
} satisfies DatasetReleaseSummary

describe('dataset release presentation', () => {
  it('formats a readable name, version, and task identifier', () => {
    expect(formatDatasetReleaseLabel(release)).toBe(
      '电梯标识分割数据集 · v0.1.3 · otis-inspection-segmentation',
    )
  })

  it('falls back to the task identifier for legacy runtime payloads', () => {
    expect(formatDatasetReleaseLabel({ ...release, display_name: '' })).toBe(
      'otis-inspection-segmentation · v0.1.3 · otis-inspection-segmentation',
    )
  })

  it('resolves a training release id and preserves unknown ids', () => {
    expect(resolveDatasetReleaseLabel(release.id, [release])).toBe(
      '电梯标识分割数据集 · v0.1.3 · otis-inspection-segmentation',
    )
    expect(resolveDatasetReleaseLabel('missing-release', [release])).toBe('missing-release')
  })

  it('keeps long dataset labels readable in the training dropdown', () => {
    const source = fs.readFileSync(path.resolve('src/pages/platform/TrainingPage.tsx'), 'utf8')

    expect(source).toContain('popupMatchSelectWidth={520}')
  })
})
