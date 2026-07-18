import { Alert, Button, Empty, Select, Tag } from 'antd'
import { Check, LockKeyhole, Pencil, RotateCcw, ScanLine, Trash2, X } from 'lucide-react'

import type { AnnotationImageApiResponse, AnnotationStatus } from '../../api'
import { formatClassLabel } from './classLabels'
import type { AnnotationInteractionState } from './annotationInteraction'
import { annotationModeLabel, classColor, type AnnotationObjectPresentation } from './annotationPresentation'

export interface AnnotationInspectorProps {
  image: AnnotationImageApiResponse
  displayNames?: Record<string, string>
  interaction: AnnotationInteractionState
  objects: AnnotationObjectPresentation[]
  busy: boolean
  onNewClassChange: (classId: number) => void
  onSelectObject: (shapeId: string) => void
  onBeginClassEdit: (classId: number) => void
  onClassDraftChange: (classId: number) => void
  onSaveClass: () => void
  onCancelClassEdit: () => void
  onDeleteObject: () => void
  onStatusChange: (status: AnnotationStatus) => void
  createControls?: React.ReactNode
}

export function AnnotationInspector(props: AnnotationInspectorProps) {
  const { image, interaction, objects, busy } = props
  const selected = objects.find((object) => object.id === interaction.selectedShapeId)
  const classOptions = image.classes.map((name, index) => ({
    value: index,
    label: <span className="annotation-class-option"><i style={{ backgroundColor: classColor(index) }} /> <b>{index}</b> {formatClassLabel(name, props.displayNames)}</span>,
  }))
  const selectedClassLabel = selected?.label ?? ''
  const createClassName = image.classes[interaction.newClassId] ?? ''

  return <>
    <div className="annotation-pane-heading">
      <strong>属性检查器</strong>
      <Tag>{image.task_type.toUpperCase()}</Tag>
    </div>

    <div className={`annotation-mode-indicator${interaction.readonly ? ' readonly' : ''}`}>
      {annotationModeLabel({
        tool: interaction.tool,
        classLabel: formatClassLabel(createClassName, props.displayNames),
        readonly: interaction.readonly,
      })}
    </div>

    <div className="annotation-summary">
      <span>状态<strong>{statusLabel(image.status)}</strong></span>
      <span>版本<strong>{image.revision}</strong></span>
      <span>对象<strong>{objects.length}</strong></span>
    </div>

    {interaction.readonly ? <ReadonlyContext selected={selected} />
      : interaction.tool !== 'select' ? <CreateContext {...props} classOptions={classOptions} />
        : selected && interaction.classDraft !== undefined ? <EditClassContext {...props} selected={selected} classOptions={classOptions} />
          : selected ? <SelectedContext {...props} selected={selected} />
            : <IdleContext />}

    <div className="annotation-section-title">标注对象</div>
    {objects.length ? <div className="annotation-shape-list">
      {objects.map((object) => <button
        key={object.id}
        type="button"
        className={object.id === interaction.selectedShapeId ? 'active' : ''}
        onClick={() => props.onSelectObject(object.id)}
        disabled={busy}
      >
        <span className="annotation-object-number" style={{ backgroundColor: object.color }}>#{object.number}</span>
        <span>{object.label}</span>
        <small>{shapeTypeLabel(object.shape.shape_type)} · {sourceLabel(object.shape.source)}</small>
      </button>)}
    </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前图片还没有标注对象" />}

    <div className="annotation-status-actions">
      {image.status !== 'reviewed' ? <Button
        type="primary"
        icon={<Check size={15} />}
        disabled={objects.length === 0 || busy}
        onClick={() => props.onStatusChange('reviewed')}
      >审核通过</Button> : <Button
        icon={<RotateCcw size={15} />}
        disabled={busy}
        onClick={() => props.onStatusChange('annotated')}
      >退回修改</Button>}
    </div>
  </>
}

function IdleContext() {
  return <div className="annotation-inspector-context">
    <ScanLine size={18} />
    <div><strong>请选择一个标注对象</strong><p>点击画布轮廓或下方对象列表进行检查。</p></div>
  </div>
}

function CreateContext(props: AnnotationInspectorProps & { classOptions: Array<{ value: number; label: React.ReactNode }> }) {
  return <section className="annotation-inspector-section">
    <h3>新建对象</h3>
    <label>新建对象类别</label>
    <Select
      value={props.interaction.newClassId >= 0 ? props.interaction.newClassId : undefined}
      options={props.classOptions}
      onChange={props.onNewClassChange}
      disabled={props.busy || props.image.classes.length === 0}
      placeholder="请选择类别"
    />
    <p className="annotation-context-hint">新对象将使用此类别。已有对象不会被修改。</p>
    {props.createControls}
  </section>
}

function SelectedContext(props: AnnotationInspectorProps & { selected: AnnotationObjectPresentation }) {
  const { selected } = props
  return <section className="annotation-selected-card">
    <header>
      <span className="annotation-object-number" style={{ backgroundColor: selected.color }}>#{selected.number}</span>
      <div><h3>对象 #{selected.number}</h3><p>{selected.label}</p></div>
    </header>
    <dl>
      <div><dt>形状</dt><dd>{shapeTypeLabel(selected.shape.shape_type)}</dd></div>
      <div><dt>来源</dt><dd>{sourceLabel(selected.shape.source)}</dd></div>
    </dl>
    <div className="annotation-selected-actions">
      <Button icon={<Pencil size={14} />} onClick={() => props.onBeginClassEdit(selected.shape.class_id)} disabled={props.busy}>修改类别</Button>
      <Button danger icon={<Trash2 size={14} />} onClick={props.onDeleteObject} disabled={props.busy}>删除对象</Button>
    </div>
  </section>
}

function EditClassContext(props: AnnotationInspectorProps & { selected: AnnotationObjectPresentation; classOptions: Array<{ value: number; label: React.ReactNode }> }) {
  const { selected } = props
  return <section className="annotation-selected-card editing">
    <header>
      <span className="annotation-object-number" style={{ backgroundColor: selected.color }}>#{selected.number}</span>
      <div><h3>修改对象 #{selected.number} 的类别</h3><p>保存前不会修改服务端数据。</p></div>
    </header>
    <label>目标类别</label>
    <Select value={props.interaction.classDraft} options={props.classOptions} onChange={props.onClassDraftChange} disabled={props.busy} />
    <div className="annotation-selected-actions">
      <Button type="primary" icon={<Check size={14} />} onClick={props.onSaveClass} loading={props.busy}>保存到对象 #{selected.number}</Button>
      <Button icon={<X size={14} />} onClick={props.onCancelClassEdit} disabled={props.busy}>取消修改</Button>
    </div>
  </section>
}

function ReadonlyContext({ selected }: { selected?: AnnotationObjectPresentation }) {
  return <Alert
    className="annotation-readonly-banner"
    type="success"
    showIcon
    icon={<LockKeyhole size={18} />}
    message="已审核，只读"
    description={selected ? `正在检查对象 #${selected.number}：${selected.label}` : '可以检查对象；如需编辑，请先点击“退回修改”。'}
  />
}

function statusLabel(status: AnnotationStatus) {
  return { pending: '待标注', annotated: '待审核', reviewed: '已审核' }[status]
}

function shapeTypeLabel(shapeType: 'box' | 'polygon') {
  return shapeType === 'box' ? '矩形' : '多边形'
}

function sourceLabel(source: 'manual' | 'sam2') {
  return source === 'sam2' ? 'SAM2' : '手动'
}
