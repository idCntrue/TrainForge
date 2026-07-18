import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { AnnotationImageApiResponse } from '../../api'
import { AnnotationInspector, type AnnotationInspectorProps } from './AnnotationInspector'
import { createAnnotationInteraction } from './annotationInteraction'
import { buildObjectPresentation } from './annotationPresentation'

const image: AnnotationImageApiResponse = {
  frame_id: 'frame-1', task_id: 'task-1', task_type: 'segment', image_path: 'frame.jpg',
  width: 1280, height: 720, status: 'annotated', revision: 3,
  classes: ['entry-light', 'safety-sign'],
  shapes: [
    { id: 'shape-1', class_id: 0, class_name: 'entry-light', shape_type: 'polygon', coordinates: [0, 0, 1, 0, 1, 1], source: 'manual', created_at: '', updated_at: '' },
    { id: 'shape-2', class_id: 1, class_name: 'safety-sign', shape_type: 'polygon', coordinates: [0, 0, 1, 0, 1, 1], source: 'sam2', created_at: '', updated_at: '' },
  ],
  created_at: '', updated_at: '',
}

const displayNames = { 'entry-light': '入口指示灯', 'safety-sign': '乘梯注意事项' }
const objects = buildObjectPresentation(image.shapes, displayNames)

function render(overrides: Partial<AnnotationInspectorProps> = {}) {
  const props: AnnotationInspectorProps = {
    image,
    displayNames,
    interaction: createAnnotationInteraction(0),
    objects,
    busy: false,
    onNewClassChange: vi.fn(),
    onSelectObject: vi.fn(),
    onBeginClassEdit: vi.fn(),
    onClassDraftChange: vi.fn(),
    onSaveClass: vi.fn(),
    onCancelClassEdit: vi.fn(),
    onDeleteObject: vi.fn(),
    onStatusChange: vi.fn(),
    ...overrides,
  }
  return renderToStaticMarkup(<AnnotationInspector {...props} />)
}

describe('AnnotationInspector', () => {
  it('shows only the create context while a drawing tool is active', () => {
    const html = render({ interaction: { ...createAnnotationInteraction(0), tool: 'polygon' } })
    expect(html).toContain('新建对象')
    expect(html).toContain('新建对象类别')
    expect(html).not.toContain('修改类别')
  })

  it('shows the selected object context without a create-class control', () => {
    const html = render({ interaction: { ...createAnnotationInteraction(0), selectedShapeId: 'shape-2' } })
    expect(html).toContain('对象 #2')
    expect(html).toContain('修改类别')
    expect(html).not.toContain('新建对象类别')
  })

  it('keeps class changes in an explicit edit context', () => {
    const html = render({ interaction: { ...createAnnotationInteraction(0), selectedShapeId: 'shape-2', classDraft: 0 } })
    expect(html).toContain('保存到对象 #2')
    expect(html).toContain('取消修改')
    expect(html).not.toContain('新建对象类别')
  })

  it('shows a prominent reviewed lock context', () => {
    const html = render({ interaction: { ...createAnnotationInteraction(0, true), selectedShapeId: 'shape-2' } })
    expect(html).toContain('已审核，只读')
    expect(html).not.toContain('修改类别')
    expect(html).not.toContain('新建对象类别')
  })

  it('shows guidance in idle selection mode', () => {
    const html = render()
    expect(html).toContain('请选择一个标注对象')
    expect(html).not.toContain('新建对象类别')
  })

  it('keeps the image summary above tall create-tool controls', () => {
    const html = render({
      interaction: { ...createAnnotationInteraction(0), tool: 'sam' },
      createControls: <div>SMART_CONTROLS</div>,
    })

    expect(html.indexOf('状态')).toBeLessThan(html.indexOf('SMART_CONTROLS'))
  })
})
