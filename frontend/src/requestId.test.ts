import { afterEach, describe, expect, it, vi } from 'vitest'

import { createRequestId } from './requestId'

describe('createRequestId', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses crypto.randomUUID when available', () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'native-uuid' })

    expect(createRequestId()).toBe('native-uuid')
  })

  it('builds an RFC 4122 UUID with getRandomValues on plain HTTP', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(1)
        return bytes
      },
    })

    expect(createRequestId()).toBe('01010101-0101-4101-8101-010101010101')
  })

  it('returns a usable request id without Web Crypto', () => {
    vi.stubGlobal('crypto', undefined)

    expect(createRequestId()).toMatch(/^request-[a-z0-9]+-[a-z0-9]+$/)
  })
})
