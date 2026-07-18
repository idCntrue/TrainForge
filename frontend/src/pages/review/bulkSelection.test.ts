import { describe, expect, it } from 'vitest'

import { applyBulkStatus, filterFrameNames, selectFrameRange } from './bulkSelection'

const frames = [
  { filename: 'a.jpg', status: 'candidate' },
  { filename: 'b.jpg', status: 'selected' },
  { filename: 'c.jpg', status: 'rejected' },
]

describe('review bulk selection', () => {
  it('filters using pending local status before persisted status', () => {
    expect(filterFrameNames(frames, { 'a.jpg': 'selected' }, 'selected')).toEqual(['a.jpg', 'b.jpg'])
    expect(filterFrameNames(frames, {}, 'rejected')).toEqual(['c.jpg'])
  })

  it('selects an inclusive shift range without dropping existing selection', () => {
    expect(selectFrameRange(['a', 'b', 'c', 'd'], ['d'], 'c', 'a')).toEqual(['d', 'a', 'b', 'c'])
  })

  it('applies one status to every selected filename', () => {
    expect(applyBulkStatus({ 'old.jpg': 'selected' }, ['a.jpg', 'b.jpg'], 'rejected/blur')).toEqual({
      'old.jpg': 'selected', 'a.jpg': 'rejected/blur', 'b.jpg': 'rejected/blur',
    })
  })
})
