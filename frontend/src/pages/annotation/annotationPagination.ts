export interface AnnotationQueuePageChange {
  reason: 'filter-change' | 'item-updated'
  page: number
  pageSize: number
  total: number
  itemStillMatches?: boolean
}

export function resolveAnnotationQueuePage(change: AnnotationQueuePageChange): number {
  if (change.reason === 'filter-change') return 1
  if (change.itemStillMatches !== false) return change.page
  const totalAfterRemoval = Math.max(0, change.total - 1)
  return Math.min(change.page, Math.max(1, Math.ceil(totalAfterRemoval / change.pageSize)))
}
