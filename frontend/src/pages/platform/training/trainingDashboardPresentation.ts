import type { TrainingArtifactApiResponse, TrainingEpochMetrics } from '../../../api'

export type SplitItem = {
  key: 'train' | 'val' | 'test'
  label: string
  count: number
  percent: number
}

export function splitPresentation(counts: Record<string, number>) {
  const definitions: Array<Pick<SplitItem, 'key' | 'label'>> = [
    { key: 'train', label: '训练集' },
    { key: 'val', label: '验证集' },
    { key: 'test', label: '测试集' },
  ]
  const total = definitions.reduce((sum, item) => sum + Math.max(0, counts[item.key] ?? 0), 0)
  let allocated = 0
  const items: SplitItem[] = definitions.map((item, index) => {
    const count = Math.max(0, counts[item.key] ?? 0)
    const percent = !total ? 0 : index === definitions.length - 1 ? 100 - allocated : Math.round((count / total) * 100)
    allocated += percent
    return { ...item, count, percent }
  })
  return { total, items }
}

export type MetricMode = 'box' | 'mask'

export function defaultMetricMode(taskType: string): MetricMode {
  return taskType === 'segment' ? 'mask' : 'box'
}

export type LossTrend = {
  state: 'improving' | 'stable' | 'worsening' | 'unavailable'
  latest: number | null
  changePercent: number | null
}

export function lossTrend(history: TrainingEpochMetrics[], key: string): LossTrend {
  const values = history
    .slice(-5)
    .map((row) => row[key])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  const latest = values.at(-1) ?? null
  if (values.length < 2 || latest == null) return { state: 'unavailable', latest, changePercent: null }
  const first = values[0]
  const denominator = Math.max(Math.abs(first), 1e-9)
  const changePercent = ((latest - first) / denominator) * 100
  const state = changePercent < -2 ? 'improving' : changePercent > 2 ? 'worsening' : 'stable'
  return { state, latest, changePercent }
}

export function resultImageGroups(artifacts: TrainingArtifactApiResponse[]) {
  const images = artifacts.filter((item) => item.kind === 'image')
  const predictions: TrainingArtifactApiResponse[] = []
  const confusion: TrainingArtifactApiResponse[] = []
  const curves: TrainingArtifactApiResponse[] = []
  const other: TrainingArtifactApiResponse[] = []
  for (const item of images) {
    const key = item.key.toLowerCase()
    if (key.includes('pred')) predictions.push(item)
    else if (key.includes('confusion')) confusion.push(item)
    else if (key.includes('curve')) curves.push(item)
    else other.push(item)
  }
  return { predictions, confusion, curves, other }
}

export function artifactGroups(artifacts: TrainingArtifactApiResponse[]) {
  const weights = artifacts.filter((item) => item.key === 'best_pt' || item.key === 'last_pt')
  const reports = artifacts.filter((item) => item.key === 'results_csv' || item.key === 'runner_log' || item.key === 'results')
  const grouped = new Set([...weights, ...reports])
  const other = artifacts.filter((item) => item.kind !== 'image' && !grouped.has(item))
  return { weights, reports, other }
}
