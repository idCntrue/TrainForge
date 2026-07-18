import type { AnnotationTool } from '../../api'

export interface AnnotationInteractionState {
  tool: AnnotationTool
  selectedShapeId?: string
  newClassId: number
  classDraft?: number
  readonly: boolean
}

export type AnnotationInteractionEvent =
  | { type: 'tool'; tool: AnnotationTool }
  | { type: 'select-shape'; shapeId?: string }
  | { type: 'begin-class-edit'; classId: number }
  | { type: 'set-class-draft'; classId: number }
  | { type: 'cancel-class-edit' }
  | { type: 'set-new-class'; classId: number }
  | { type: 'image-change'; classCount: number; readonly?: boolean }
  | { type: 'escape' }

export function createAnnotationInteraction(classCount: number, readonly = false): AnnotationInteractionState {
  return { tool: 'select', selectedShapeId: undefined, newClassId: classCount > 0 ? 0 : -1, classDraft: undefined, readonly }
}

export function reduceAnnotationInteraction(state: AnnotationInteractionState, event: AnnotationInteractionEvent): AnnotationInteractionState {
  if (event.type === 'image-change') return createAnnotationInteraction(event.classCount, Boolean(event.readonly))
  if (event.type === 'select-shape') return { ...state, tool: 'select', selectedShapeId: event.shapeId, classDraft: undefined }
  if (state.readonly) return state

  if (event.type === 'tool') {
    return { ...state, tool: event.tool, selectedShapeId: undefined, classDraft: undefined }
  }
  if (event.type === 'begin-class-edit') {
    if (!state.selectedShapeId || state.tool !== 'select') return state
    return { ...state, classDraft: event.classId }
  }
  if (event.type === 'set-class-draft') {
    if (state.classDraft === undefined) return state
    return { ...state, classDraft: event.classId }
  }
  if (event.type === 'cancel-class-edit') return { ...state, classDraft: undefined }
  if (event.type === 'set-new-class') return { ...state, newClassId: event.classId }
  if (event.type === 'escape') {
    if (state.classDraft !== undefined) return { ...state, classDraft: undefined }
    if (state.tool !== 'select') return { ...state, tool: 'select', selectedShapeId: undefined }
    return { ...state, selectedShapeId: undefined }
  }
  return state
}
