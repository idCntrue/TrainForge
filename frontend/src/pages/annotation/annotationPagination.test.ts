import { describe, expect, it } from 'vitest'

import { resolveAnnotationQueuePage } from './annotationPagination'

describe('annotation queue page resolution', () => {
  it('resets to page one when the task or status filter changes', () => {
    expect(resolveAnnotationQueuePage({ reason: 'filter-change', page: 4, pageSize: 30, total: 120 })).toBe(1)
  })

  it('keeps the page when an updated item still matches the active filter', () => {
    expect(resolveAnnotationQueuePage({ reason: 'item-updated', page: 3, pageSize: 2, total: 5, itemStillMatches: true })).toBe(3)
  })

  it('moves to the previous page when removing the only item on the final page', () => {
    expect(resolveAnnotationQueuePage({ reason: 'item-updated', page: 3, pageSize: 2, total: 5, itemStillMatches: false })).toBe(2)
  })
})
