import { describe, expect, it } from 'vitest'

import { historyTravel } from './navigationHistory'

describe('guarded browser history travel', () => {
  it('restores the current position without adding a history entry', () => {
    expect(historyTravel(4, 3)).toEqual({ restoreDelta: 1, resumeDelta: -1 })
    expect(historyTravel(4, 2)).toEqual({ restoreDelta: 2, resumeDelta: -2 })
  })

  it('supports a guarded forward navigation', () => {
    expect(historyTravel(2, 5)).toEqual({ restoreDelta: -3, resumeDelta: 3 })
  })

  it('returns null when positions are unavailable or unchanged', () => {
    expect(historyTravel(undefined, 1)).toBeNull()
    expect(historyTravel(2, undefined)).toBeNull()
    expect(historyTravel(2, 2)).toBeNull()
  })
})
