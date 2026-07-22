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

export type TrainingMetricCard = {
  key: string
  label: string
  value: number | null
  help: string
}

export type TrainingLossCard = TrainingMetricCard & { trend: LossTrend }
export type TrainingLogLevel = 'info' | 'epoch' | 'warning' | 'error'
export type TrainingLogLine = { number: number; text: string; level: TrainingLogLevel }
export type TrainingLogFilter = {
  mode: 'live' | 'diagnostic'
  level: 'all' | TrainingLogLevel
  query: string
}

export function latestFiniteMetric(history: TrainingEpochMetrics[], key: string): number | null {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const value = history[index][key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}

const qualityDefinitions: Record<'box' | 'mask', Array<Omit<TrainingMetricCard, 'value'>>> = {
  mask: [
    { key: 'map50_mask', label: 'Mask mAP50', help: '衡量分割轮廓在 IoU 0.50 条件下的整体识别能力，通常越高越好。' },
    { key: 'map50_95_mask', label: 'Mask mAP50-95', help: '在多个更严格 IoU 条件下评估分割精度，比 mAP50 更严格。' },
  ],
  box: [
    { key: 'map50_box', label: 'Box mAP50', help: '衡量目标框在 IoU 0.50 条件下的整体识别能力，通常越高越好。' },
    { key: 'map50_95_box', label: 'Box mAP50-95', help: '在多个更严格 IoU 条件下评估目标框定位精度。' },
  ],
}

export function metricCards(taskType: string, history: TrainingEpochMetrics[]): TrainingMetricCard[] {
  const definitions = taskType === 'segment'
    ? [...qualityDefinitions.mask, ...qualityDefinitions.box]
    : qualityDefinitions.box
  return definitions.map((item) => ({ ...item, value: latestFiniteMetric(history, item.key) }))
}

const lossDefinitions: Array<Omit<TrainingMetricCard, 'value'> & { segmentOnly?: boolean }> = [
  { key: 'train_box_loss', label: 'Box Loss', help: '反映目标位置偏差。应关注连续多轮趋势，不宜跨任务比较绝对值。' },
  { key: 'train_seg_loss', label: 'Mask Loss', help: '反映预测轮廓与标注轮廓之间的偏差。', segmentOnly: true },
  { key: 'train_cls_loss', label: 'Class Loss', help: '反映模型类别判断的偏差。' },
  { key: 'train_dfl_loss', label: 'DFL Loss', help: '反映边界框细粒度定位的偏差。' },
]

export function lossCards(taskType: string, history: TrainingEpochMetrics[]): TrainingLossCard[] {
  return lossDefinitions
    .filter((item) => !item.segmentOnly || taskType === 'segment')
    .map(({ segmentOnly: _segmentOnly, ...item }) => ({
      ...item,
      value: latestFiniteMetric(history, item.key),
      trend: lossTrend(history, item.key),
    }))
    .filter((item) => item.value != null)
}

export function classifyLogLine(text: string): TrainingLogLevel {
  if (/traceback|error|exception|failed|fatal|out\s*of\s*memory|outofmemory|resource_limit/i.test(text)) return 'error'
  if (/\bwarn(?:ing)?\b|警告/i.test(text)) return 'warning'
  if (/\bepoch\b|\d+\s*\/\s*\d+.*(?:gpu_mem|box_loss|seg_loss|cls_loss|dfl_loss)/i.test(text)) return 'epoch'
  return 'info'
}

export function filterLogLines(lines: string[], filter: TrainingLogFilter): TrainingLogLine[] {
  const query = filter.query.trim().toLocaleLowerCase()
  return lines
    .map((line, index) => ({ number: index + 1, text: line, level: classifyLogLine(line) }))
    .filter((line) => filter.mode === 'live' || line.level === 'warning' || line.level === 'error')
    .filter((line) => filter.level === 'all' || line.level === filter.level)
    .filter((line) => !query || line.text.toLocaleLowerCase().includes(query))
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
