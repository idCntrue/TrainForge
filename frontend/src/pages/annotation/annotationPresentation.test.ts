import { describe, expect, it } from 'vitest'

import type { AnnotationShapeApiResponse } from '../../api'
import { annotationModeLabel, buildObjectPresentation, classColor, findCreatedShapeId, shapeVisualStyle } from './annotationPresentation'

const shape = (id: string, classId: number, className: string): AnnotationShapeApiResponse => ({
  id, class_id: classId, class_name: className, shape_type: 'polygon', coordinates: [0, 0, 1, 0, 1, 1], source: 'manual', created_at: '', updated_at: '',
})

describe('annotation presentation', () => {
  it('uses stable distinguishable class colors', () => {
    expect(classColor(0)).toMatch(/^#[0-9a-f]{6}$/i)
    expect(classColor(0)).not.toBe(classColor(1))
    expect(classColor(0)).toBe(classColor(8))
  })

  it('numbers objects in server response order and localizes labels', () => {
    const items = buildObjectPresentation(
      [shape('shape-a', 1, 'entry-light'), shape('shape-b', 2, 'safety-sign')],
      { 'safety-sign': '乘梯注意事项' },
    )

    expect(items[1]).toMatchObject({ id: 'shape-b', number: 2, label: '乘梯注意事项（safety-sign）' })
  })

  it('finds the created object by ID difference instead of array position', () => {
    expect(findCreatedShapeId(['old-a', 'old-b'], ['new-c', 'old-a', 'old-b'])).toBe('new-c')
  })

  it('describes the active create and readonly modes', () => {
    expect(annotationModeLabel({ tool: 'polygon', classLabel: '乘梯注意事项', readonly: false })).toBe('新建多边形 · 类别：乘梯注意事项')
    expect(annotationModeLabel({ tool: 'select', classLabel: '', readonly: true })).toBe('已审核 · 只读')
  })

  it('keeps class color while selection adds a separate emphasis', () => {
    expect(shapeVisualStyle('#dc2626', false)).toEqual({
      classStroke: '#dc2626', fill: 'rgba(220,38,38,0.12)', strokeWidth: 2, selectionStroke: undefined,
    })
    expect(shapeVisualStyle('#dc2626', true)).toEqual({
      classStroke: '#dc2626', fill: 'rgba(220,38,38,0.2)', strokeWidth: 3, selectionStroke: '#34d399',
    })
  })
})
