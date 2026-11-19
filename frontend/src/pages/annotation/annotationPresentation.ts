import type { AnnotationShapeApiResponse, AnnotationTool } from '../../api'
import { formatClassLabel } from './classLabels'

const CLASS_COLORS = [
  '#d97706',
  '#2563eb',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#65a30d',
  '#db2777',
  '#475569',
]

export interface AnnotationObjectPresentation {
  id: string
  number: number
  color: string
  label: string
  shape: AnnotationShapeApiResponse
}

export function classColor(classId: number): string {
  const index = Math.abs(Math.trunc(classId)) % CLASS_COLORS.length
  return CLASS_COLORS[index]
}

export function buildObjectPresentation(
  shapes: AnnotationShapeApiResponse[],
  displayNames: Record<string, string> = {},
): AnnotationObjectPresentation[] {
  return shapes.map((shape, index) => ({
    id: shape.id,
    number: index + 1,
    color: classColor(shape.class_id),
    label: formatClassLabel(shape.class_name, displayNames),
    shape,
  }))
}

export function findCreatedShapeId(beforeIds: string[], afterIds: string[]): string | undefined {
  const previous = new Set(beforeIds)
  return afterIds.find((id) => !previous.has(id))
}

export function shapeVisualStyle(color: string, selected: boolean, draft = false) {
  const red = Number.parseInt(color.slice(1, 3), 16)
  const green = Number.parseInt(color.slice(3, 5), 16)
  const blue = Number.parseInt(color.slice(5, 7), 16)
  const fillAlpha = selected ? 0.2 : draft ? 0.06 : 0.12
  return {
    classStroke: color,
    fill: `rgba(${red},${green},${blue},${selected ? fillAlpha : fillAlpha})`,
    strokeWidth: selected ? 3 : draft ? 1.5 : 2,
    selectionStroke: selected ? '#34d399' : undefined,
    dash: draft ? [6, 4] : undefined,
  }
}

export function shapeLabelText(object: AnnotationObjectPresentation): string {
  const base = `#${object.number} ${object.label}`
  if (object.shape.status !== 'draft') return base
  const confidence = typeof object.shape.confidence === 'number' ? ` · ${Math.round(object.shape.confidence * 100)}%` : ''
  return `${base}${confidence} · 待确认`
}

const toolLabels: Record<Exclude<AnnotationTool, 'select'>, string> = {
  box: '新建矩形',
  polygon: '新建多边形',
  sam: 'SAM2 智能分割',
}

export function annotationModeLabel({
  tool,
  classLabel,
  readonly,
}: {
  tool: AnnotationTool
  classLabel: string
  readonly: boolean
}): string {
  if (readonly) return '已审核 · 只读'
  if (tool === 'select') return '选择模式 · 点击对象进行检查'
  return `${toolLabels[tool]} · 类别：${classLabel}`
}
