const labels: Record<string, string> = {
  selected: '已保留',
  candidate: '待筛选',
  duplicate: '重复帧',
  'rejected/blur': '模糊',
  'rejected/no-target': '无目标',
  'rejected/privacy': '隐私风险',
  'rejected/duplicate': '重复帧',
  'rejected/other': '其他原因',
}

export function reviewStatusLabel(status: string): string {
  return labels[status] ?? status.split('/').pop() ?? status
}
