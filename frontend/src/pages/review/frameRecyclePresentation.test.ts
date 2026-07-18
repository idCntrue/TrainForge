import { describe, expect, it } from 'vitest'

import {
  formatRecycleBytes,
  formatRecycleExpiry,
  recyclePurgeConfirmation,
  recycleTrashConfirmation,
} from './frameRecyclePresentation'

describe('frame recycle presentation', () => {
  it('explains the seven-day retention period and selected count in Chinese', () => {
    expect(recycleTrashConfirmation(12)).toContain('12 张')
    expect(recycleTrashConfirmation(12)).toContain('7 天')
  })

  it('makes permanent deletion consequences explicit', () => {
    expect(recyclePurgeConfirmation(3)).toBe('将永久删除 3 张图片及其原标注，删除后无法恢复。')
  })

  it('formats storage size for ordinary users', () => {
    expect(formatRecycleBytes(0)).toBe('0 B')
    expect(formatRecycleBytes(1536)).toBe('1.5 KB')
    expect(formatRecycleBytes(2 * 1024 * 1024)).toBe('2 MB')
  })

  it('formats expiry as a concrete local time', () => {
    expect(formatRecycleExpiry('2026-07-23T04:30:00Z')).toContain('2026-07-23')
    expect(formatRecycleExpiry(null)).toBe('--')
  })
})
