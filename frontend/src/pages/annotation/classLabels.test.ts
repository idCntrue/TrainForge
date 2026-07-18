import { describe, expect, it } from 'vitest'

import { formatClassLabel, resolveAnnotationTaskId } from './classLabels'

describe('formatClassLabel', () => {
  it('shows the localized name before the stable class identifier', () => {
    expect(formatClassLabel('scratch', { scratch: '划痕' })).toBe('划痕（scratch）')
    expect(formatClassLabel('dent', {})).toBe('dent')
  })
})

describe('resolveAnnotationTaskId', () => {
  it('falls back to the current image task when the toolbar has no selection', () => {
    expect(resolveAnnotationTaskId(undefined, 'example-segmentation')).toBe('example-segmentation')
    expect(resolveAnnotationTaskId('selected-task', 'image-task')).toBe('selected-task')
  })
})
