export function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return '计算中'
  const rounded = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  return minutes ? `${minutes}分 ${remainder}秒` : `${remainder}秒`
}

type RunStatus = 'queued' | 'running' | 'evaluating' | 'exporting' | 'verifying' | 'completed' | 'failed' | 'cancelled' | 'interrupted'

export function epochProgressText(status: RunStatus, epoch: number, totalEpochs: number): string {
  const progress = `${epoch} / ${totalEpochs}`
  return status === 'completed' && epoch < totalEpochs ? `${progress}（已提前停止）` : progress
}

export function timingText(
  status: RunStatus,
  seconds: number | null | undefined,
  kind: 'epoch' | 'eta',
): string {
  if (seconds != null) return formatDuration(seconds)
  if (status === 'completed') return kind === 'eta' ? '已完成' : '--'
  if (status === 'failed' || status === 'cancelled' || status === 'interrupted') return '已结束'
  return '计算中'
}

export function metricText(value: number | null | undefined) {
  return value == null ? '待生成' : value.toFixed(4)
}

const labels: Record<string, string> = {
  best_pt: '最佳权重 best.pt', last_pt: '最终权重 last.pt', results: '训练结果总览',
  results_csv: '逐轮指标 CSV', runner_log: '完整运行日志', run_manifest: '训练清单',
  confusion_matrix: '混淆矩阵', confusion_matrix_normalized: '归一化混淆矩阵',
  PR_curve: '精确率-召回率曲线', P_curve: '精确率曲线', R_curve: '召回率曲线', F1_curve: 'F1 分数曲线',
  val_batch0_pred: '验证集预测样例', val_batch0_labels: '验证集标注样例',
}

export function artifactLabel(key: string) {
  return labels[key] ?? key.replaceAll('_', ' ')
}
