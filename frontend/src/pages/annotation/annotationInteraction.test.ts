import { describe, expect, it } from 'vitest'

import { createAnnotationInteraction, reduceAnnotationInteraction } from './annotationInteraction'

describe('annotation interaction state', () => {
  it('clears the old target and class draft when a drawing tool starts', () => {
    const current = { ...createAnnotationInteraction(5), selectedShapeId: 'shape-1', classDraft: 3 }

    expect(reduceAnnotationInteraction(current, { type: 'tool', tool: 'polygon' })).toEqual({
      tool: 'polygon', selectedShapeId: undefined, newClassId: 0, classDraft: undefined, readonly: false,
    })
  })

  it('forces pointer mode when an object is selected', () => {
    const current = { ...createAnnotationInteraction(5), tool: 'polygon' as const, newClassId: 2 }

    expect(reduceAnnotationInteraction(current, { type: 'select-shape', shapeId: 'shape-2' }))
      .toMatchObject({ tool: 'select', selectedShapeId: 'shape-2', classDraft: undefined })
  })

  it('resets selection and an out-of-range class on image changes', () => {
    const current = { ...createAnnotationInteraction(5), selectedShapeId: 'shape-1', newClassId: 4, classDraft: 3 }

    expect(reduceAnnotationInteraction(current, { type: 'image-change', classCount: 2 })).toEqual({
      tool: 'select', selectedShapeId: undefined, newClassId: 0, classDraft: undefined, readonly: false,
    })
  })

  it('keeps class changes local until the caller explicitly saves', () => {
    const selected = reduceAnnotationInteraction(
      { ...createAnnotationInteraction(3), selectedShapeId: 'shape-1' },
      { type: 'begin-class-edit', classId: 1 },
    )

    expect(reduceAnnotationInteraction(selected, { type: 'set-class-draft', classId: 2 }))
      .toMatchObject({ selectedShapeId: 'shape-1', classDraft: 2 })
  })

  it('uses escape to cancel a class draft before clearing selection', () => {
    const editing = { ...createAnnotationInteraction(3), selectedShapeId: 'shape-1', classDraft: 2 }
    const cancelled = reduceAnnotationInteraction(editing, { type: 'escape' })

    expect(cancelled).toMatchObject({ selectedShapeId: 'shape-1', classDraft: undefined })
    expect(reduceAnnotationInteraction(cancelled, { type: 'escape' }).selectedShapeId).toBeUndefined()
  })

  it('allows inspection but refuses mutation states for reviewed images', () => {
    const readonly = reduceAnnotationInteraction(createAnnotationInteraction(3), { type: 'image-change', classCount: 3, readonly: true })
    const selected = reduceAnnotationInteraction(readonly, { type: 'select-shape', shapeId: 'shape-1' })

    expect(selected).toMatchObject({ readonly: true, tool: 'select', selectedShapeId: 'shape-1' })
    expect(reduceAnnotationInteraction(selected, { type: 'tool', tool: 'polygon' })).toEqual(selected)
    expect(reduceAnnotationInteraction(selected, { type: 'begin-class-edit', classId: 1 })).toEqual(selected)
  })
})
