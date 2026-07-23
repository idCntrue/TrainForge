import { describe, expect, it } from 'vitest'

import { nextPatchVersion } from './modelVersioning'

describe('model versioning', () => {
  it('suggests the next patch version for a training run', () => {
    expect(nextPatchVersion(['1.0.0', '1.0.2', '2.1.4'])).toBe('2.1.5')
  })

  it('starts at 1.0.0 when no semantic versions exist', () => {
    expect(nextPatchVersion(['draft', '1.0'])).toBe('1.0.0')
  })
})
