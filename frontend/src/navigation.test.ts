import { describe, expect, it } from 'vitest'

import { pathForView, viewFromPath } from './navigation'

describe('workspace URL navigation', () => {
  it('maps every primary workspace to a stable path', () => {
    expect(pathForView('dashboard')).toBe('/dashboard')
    expect(pathForView('review')).toBe('/review')
    expect(pathForView('annotation')).toBe('/annotation')
    expect(pathForView('training')).toBe('/training')
  })

  it('restores a workspace from direct and nested paths', () => {
    expect(viewFromPath('/')).toBe('dashboard')
    expect(viewFromPath('/review/batch-20260717')).toBe('review')
    expect(viewFromPath('/training/run-42')).toBe('training')
  })

  it('falls back to the dashboard for unknown paths', () => {
    expect(viewFromPath('/not-a-workspace')).toBe('dashboard')
  })
})
