export interface SplitRatios { train: number; val: number; test: number }

export function validateSplitRatios(ratios: SplitRatios) {
  if (Object.values(ratios).some((value) => value < 0 || value > 100)) return '比例必须在 0% 到 100% 之间'
  if (ratios.train + ratios.val + ratios.test !== 100) return '训练集、验证集和测试集比例必须合计 100%'
  return undefined
}

export function previewSplitCounts(total: number, ratios: SplitRatios): SplitRatios {
  const keys: Array<keyof SplitRatios> = ['train', 'val', 'test']
  const raw = keys.map((key) => ({ key, value: total * ratios[key] / 100 }))
  const result: SplitRatios = { train: 0, val: 0, test: 0 }
  raw.forEach(({ key, value }) => { result[key] = Math.floor(value) })
  let remaining = total - Object.values(result).reduce((sum, value) => sum + value, 0)
  for (const item of [...raw].sort((a, b) => (b.value % 1) - (a.value % 1))) {
    if (remaining-- <= 0) break
    result[item.key] += 1
  }
  return result
}
