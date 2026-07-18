import { describe, expect, it } from 'vitest'

import { buildDisplayNamePayload, taskDisplayNameRows } from './taskDisplayNames'

describe('task display name editing', () => {
  it('preserves stable class IDs and order in edit rows', () => {
    expect(taskDisplayNameRows(['elevator-id-tag', 'safety-certificate'], {
      'elevator-id-tag': '电梯编号标签',
    })).toEqual([
      { classId: 0, className: 'elevator-id-tag', displayName: '电梯编号标签' },
      { classId: 1, className: 'safety-certificate', displayName: '' },
    ])
  })

  it('trims names and omits blank mappings from the API payload', () => {
    expect(buildDisplayNamePayload([
      { classId: 0, className: 'elevator-id-tag', displayName: '  电梯编号标签 ' },
      { classId: 1, className: 'safety-certificate', displayName: ' ' },
    ])).toEqual({ 'elevator-id-tag': '电梯编号标签' })
  })
})
