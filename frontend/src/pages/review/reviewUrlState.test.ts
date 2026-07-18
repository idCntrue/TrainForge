import { describe, expect, it } from 'vitest'

import { parseReviewUrlState, reviewUrlSearch } from './reviewUrlState'

describe('review URL state', () => {
  it('round-trips the current review context', () => {
    const search = reviewUrlSearch({ batch: 'batch 01', status: 'selected', page: 3, search: 'door plate' })
    expect(parseReviewUrlState(search)).toEqual({ batch: 'batch 01', status: 'selected', page: 3, search: 'door plate' })
  })

  it('uses safe defaults for missing or invalid parameters', () => {
    expect(parseReviewUrlState('?page=-4&status=unknown')).toEqual({ batch: null, status: 'all', page: 1, search: '' })
  })

  it('omits default values to keep URLs readable', () => {
    expect(reviewUrlSearch({ batch: null, status: 'all', page: 1, search: '' })).toBe('')
  })
})
