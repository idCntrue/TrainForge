import { describe, expect, it } from 'vitest'

import { MOBILE_VIEWPORT_QUERY, readMobileViewport } from './useMobileViewport'

describe('mobile viewport', () => {
  it('uses the application mobile breakpoint', () => {
    expect(MOBILE_VIEWPORT_QUERY).toBe('(max-width: 900px)')
  })

  it('reads the current media query match', () => {
    expect(readMobileViewport({ matches: true })).toBe(true)
    expect(readMobileViewport({ matches: false })).toBe(false)
  })
})
