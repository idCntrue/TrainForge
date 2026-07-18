const statusLabels: Record<string, string> = {
  queued: '排队中', running: '训练中', evaluating: '正在评估', exporting: '正在导出', verifying: '正在校验',
  completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断', candidate: '候选',
  published: '已发布', blocked: '未通过', archived: '已归档', passed: '已通过', pending: '待处理',
}

const phaseLabels: Record<string, string> = {
  queued: '等待训练资源', preparing: '正在准备训练资源', training: '正在训练模型',
  evaluation: '正在使用验证集评估模型', evaluating: '正在评估模型',
  test_evaluation: '正在使用测试集评估最佳权重', exporting: '正在导出模型',
  artifacts: '正在整理训练产物', verification: '正在校验训练结果', verifying: '正在校验训练结果',
  completed: '训练流程已完成', failed: '训练流程失败', cancelled: '训练已取消', interrupted: '训练已中断',
}

export function statusLabel(status: string): string {
  return statusLabels[status] ?? status
}

export function phaseLabel(phase: string): string {
  return phaseLabels[phase] ?? statusLabels[phase] ?? phase
}
