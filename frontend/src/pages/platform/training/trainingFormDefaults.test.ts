import { describe, expect, it } from 'vitest'

import { trainingFormInitialValues } from './trainingFormDefaults'

describe('training form defaults', () => {
  it('requires an explicit official model and starts with the CPU balanced preset', () => {
    expect(trainingFormInitialValues.baseModel).toBeUndefined()
    expect(trainingFormInitialValues.device).toBe('cpu')
    expect(trainingFormInitialValues.batch).toBe(2)
    expect(trainingFormInitialValues.imageSize).toBe(640)
    expect(trainingFormInitialValues.epochs).toBe(150)
    expect(trainingFormInitialValues.presetId).toBe('cpu-balanced')
  })
})
