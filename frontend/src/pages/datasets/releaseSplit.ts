type ReleaseSplitSummary = {
  requested_ratios: Record<string, number> | null
  actual_ratios: Record<string, number>
  split_counts: Record<string, number>
}

const splitLabels: Record<string, string> = {
  train: '训练',
  val: '验证',
  test: '测试',
}

export function formatReleaseSplit(release: ReleaseSplitSummary) {
  if (!release.requested_ratios || Object.keys(release.split_counts).length === 0) {
    return '历史版本未记录'
  }

  return ['train', 'val', 'test']
    .filter((split) => (release.requested_ratios?.[split] ?? 0) > 0)
    .map((split) => `${splitLabels[split]} ${release.split_counts[split] ?? 0} (${release.requested_ratios?.[split]}%)`)
    .join(' / ')
}
