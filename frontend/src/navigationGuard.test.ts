import { describe, expect, it } from 'vitest'

import { navigationDecision } from './navigationGuard'

describe('unsaved navigation guard', () => {
  it('allows navigation when there are no pending changes', () => {
    expect(navigationDecision(0, 'review', 'training')).toBe('navigate')
  })

  it('does not interrupt navigation within the same workspace', () => {
    expect(navigationDecision(12, 'review', 'review')).toBe('stay')
  })

  it('requires confirmation before leaving pending review changes', () => {
    expect(navigationDecision(12, 'review', 'annotation')).toBe('confirm')
  })
})
