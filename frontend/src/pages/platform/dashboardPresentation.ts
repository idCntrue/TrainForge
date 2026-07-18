type StageTotals = { datasetReleases: number; models: number; inferenceRuns: number }

export function workflowStages(totals: StageTotals) {
  const dataDone = totals.datasetReleases > 0
  const modelDone = totals.models > 0
  const inferenceDone = totals.inferenceRuns > 0
  return [
    { key: 'data', label: '数据准备', state: dataDone ? 'done' : 'current', detail: dataDone ? `${totals.datasetReleases} 个数据集版本` : '任务、数据、筛选与标注' },
    { key: 'model', label: '模型开发', state: modelDone ? 'done' : dataDone ? 'current' : 'pending', detail: modelDone ? `${totals.models} 个候选或已发布模型` : '训练、评估与模型门禁' },
    { key: 'inference', label: '推理验证', state: inferenceDone ? 'done' : modelDone ? 'current' : 'pending', detail: inferenceDone ? `${totals.inferenceRuns} 次推理运行` : '图片、批量图片与视频验证' },
  ] as const
}

export function releaseFunnel(total: number, published: number) {
  const safeTotal = Math.max(0, total)
  const safePublished = Math.min(safeTotal, Math.max(0, published))
  return {
    total: safeTotal,
    published: safePublished,
    pending: safeTotal - safePublished,
    rate: safeTotal ? Math.round((safePublished / safeTotal) * 100) : 0,
  }
}
