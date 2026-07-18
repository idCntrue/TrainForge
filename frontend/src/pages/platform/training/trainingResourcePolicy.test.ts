import { describe, expect, it } from 'vitest'

import { cpuTrainingPolicy, normalizeCpuTrainingValues } from './trainingResourcePolicy'

describe('CPU training resource policy', () => {
  it('uses task-specific defaults and limits', () => {
    expect(cpuTrainingPolicy('detect')).toEqual({ defaultBatch: 2, maxBatch: 4, defaultImageSize: 320, maxImageSize: 640 })
    expect(cpuTrainingPolicy('segment')).toEqual({ defaultBatch: 1, maxBatch: 1, defaultImageSize: 320, maxImageSize: 640 })
  })

  it('keeps legal manual values and resets unsafe values', () => {
    expect(normalizeCpuTrainingValues('segment', { batch: 1, imageSize: 512 })).toEqual({ batch: 1, imageSize: 512 })
    expect(normalizeCpuTrainingValues('segment', { batch: 3, imageSize: 672 })).toEqual({ batch: 1, imageSize: 320 })
  })
})
