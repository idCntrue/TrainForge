import { describe, expect, it } from 'vitest'

import { GATEWAY_UPLOAD_LIMIT_BYTES, IMAGE_UPLOAD_GUIDANCE, IMAGE_UPLOAD_LIMIT_BYTES, uploadLimitError } from './uploadPolicy'

describe('upload preflight policy', () => {
  it('matches the backend single-image limit', () => {
    expect(IMAGE_UPLOAD_LIMIT_BYTES).toBe(50 * 1024 * 1024)
    expect(uploadLimitError([{ name: 'large.jpg', size: IMAGE_UPLOAD_LIMIT_BYTES + 1 }], 'image')).toContain('large.jpg')
  })

  it('matches the nginx total request limit', () => {
    expect(GATEWAY_UPLOAD_LIMIT_BYTES).toBe(20 * 1024 * 1024 * 1024)
    expect(uploadLimitError([{ name: 'archive.zip', size: GATEWAY_UPLOAD_LIMIT_BYTES + 1 }], 'archive')).toContain('20 GB')
  })

  it('accepts files within established limits', () => {
    expect(uploadLimitError([{ name: 'ok.jpg', size: 1024 }], 'image')).toBeNull()
  })

  it('states both image and request limits before selection', () => {
    expect(IMAGE_UPLOAD_GUIDANCE).toContain('单张不超过 50 MB')
    expect(IMAGE_UPLOAD_GUIDANCE).toContain('总计不超过 20 GB')
  })
})
