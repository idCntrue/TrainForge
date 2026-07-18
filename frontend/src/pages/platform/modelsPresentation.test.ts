import { describe, expect, it } from 'vitest'
import { publicationPresentation } from './modelsPresentation'

describe('model publication presentation', () => {
  it('publishes ready models normally', () => {
    expect(publicationPresentation('ready').requiresConfirmation).toBe(false)
  })

  it('requires confirmation for weak or insufficient evidence', () => {
    expect(publicationPresentation('needs_improvement').requiresConfirmation).toBe(true)
    expect(publicationPresentation('insufficient_evidence').requiresConfirmation).toBe(true)
  })
})
