import { describe, expect, it } from 'vitest'

import { trainingFormInitialValues } from './trainingFormDefaults'

describe('training form defaults', () => {
  it('requires an explicit official model and starts on CPU', () => {
    expect(trainingFormInitialValues.baseModel).toBeUndefined()
    expect(trainingFormInitialValues.device).toBe('cpu')
    expect(trainingFormInitialValues.batch).toBe(2)
    expect(trainingFormInitialValues.imageSize).toBe(320)
  })
})
