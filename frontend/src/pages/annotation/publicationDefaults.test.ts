import { describe, expect, it } from 'vitest'

import { createNativeExportName, nextDatasetVersion } from './publicationDefaults'

describe('annotation publication defaults', () => {
  it('suggests the next patch version for the selected task', () => {
    expect(nextDatasetVersion([
      { task_id: 'inspection', version: '0.1.0' },
      { task_id: 'other', version: '9.0.0' },
      { task_id: 'inspection', version: '0.1.2' },
    ], 'inspection')).toBe('0.1.3')
    expect(nextDatasetVersion([], 'inspection')).toBe('0.1.0')
  })

  it('creates a unique timestamped native export name', () => {
    expect(createNativeExportName(new Date(2026, 6, 14, 14, 30, 12, 123))).toBe('native-reviewed-20260714-143012-123')
  })
})
