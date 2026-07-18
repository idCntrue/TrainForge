export type ReviewStatusFilter = 'all' | 'candidate' | 'selected' | 'rejected'

interface ReviewFrameLike {
  filename: string
  status: string
}

export function effectiveFrameStatus(frame: ReviewFrameLike, pending: Record<string, string>): string {
  return pending[frame.filename] ?? frame.status
}

export function filterFrameNames(frames: ReviewFrameLike[], pending: Record<string, string>, filter: ReviewStatusFilter): string[] {
  return frames.filter((frame) => {
    const status = effectiveFrameStatus(frame, pending)
    if (filter === 'all') return true
    if (filter === 'rejected') return status.startsWith('rejected')
    return status === filter
  }).map((frame) => frame.filename)
}

export function selectFrameRange(visibleNames: string[], selectedNames: string[], targetName: string, anchorName: string): string[] {
  const anchorIndex = visibleNames.indexOf(anchorName)
  const targetIndex = visibleNames.indexOf(targetName)
  if (anchorIndex < 0 || targetIndex < 0) return selectedNames.includes(targetName) ? selectedNames : [...selectedNames, targetName]
  const start = Math.min(anchorIndex, targetIndex)
  const end = Math.max(anchorIndex, targetIndex)
  const selected = new Set(selectedNames)
  visibleNames.slice(start, end + 1).forEach((name) => selected.add(name))
  return [...selected]
}

export function applyBulkStatus(pending: Record<string, string>, selectedNames: string[], status: string): Record<string, string> {
  const next = { ...pending }
  selectedNames.forEach((name) => { next[name] = status })
  return next
}
