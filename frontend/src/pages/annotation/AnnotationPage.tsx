import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { Alert, Button, Empty, Input, InputNumber, List, Modal, Pagination, Segmented, Select, Slider, Space, Tag, Tooltip, message } from 'antd'
import { ArrowLeft, Box, MousePointer2, Pentagon, Redo2, RotateCcw, Sparkles, Undo2, Upload } from 'lucide-react'

import { api, type AnnotationImageApiResponse, type AnnotationImageSummaryApiResponse, type AnnotationShapeApiResponse, type AnnotationStatus, type AnnotationTool, type TaskSummary } from '../../api'
import AnnotationCanvas from './AnnotationCanvas'
import { AnnotationInspector } from './AnnotationInspector'
import { isPointInsidePolygon } from './annotationGeometry'
import { resolveAnnotationTaskId } from './classLabels'
import { createAnnotationInteraction, reduceAnnotationInteraction } from './annotationInteraction'
import { buildObjectPresentation, findCreatedShapeId } from './annotationPresentation'
import { createNativeExportName, nextDatasetVersion } from './publicationDefaults'
import { previewSplitCounts, validateSplitRatios, type SplitRatios } from './splitRatios'
import { resolveAnnotationQueuePage } from './annotationPagination'

const statusLabels: Record<AnnotationStatus, string> = { pending: '待标注', annotated: '待审核', reviewed: '已审核' }

export default function AnnotationPage({ tasks, onNavigate, refreshDashboard }: { tasks: TaskSummary[]; onNavigate: (view: 'review' | 'training') => void; refreshDashboard: () => void }) {
  const [taskId, setTaskId] = useState<string>()
  const [status, setStatus] = useState<AnnotationStatus>()
  const [images, setImages] = useState<AnnotationImageSummaryApiResponse[]>([])
  const [current, setCurrent] = useState<AnnotationImageApiResponse>()
  const [page, setPage] = useState(1)
  const [pageSize] = useState(30)
  const [total, setTotal] = useState(0)
  const [statusCounts, setStatusCounts] = useState<Record<AnnotationStatus, number>>({ pending: 0, annotated: 0, reviewed: 0 })
  const [queueLoading, setQueueLoading] = useState(false)
  const queueRequestId = useRef(0)
  const detailRequestId = useRef(0)
  const [interaction, dispatchInteraction] = useReducer(reduceAnnotationInteraction, 0, createAnnotationInteraction)
  const [samModel, setSamModel] = useState<'sam2_t.pt' | 'sam2_s.pt'>('sam2_t.pt')
  const [samPendingPoint, setSamPendingPoint] = useState<[number, number]>()
  const [samPrompts, setSamPrompts] = useState<Array<{ point: [number, number]; label: 0 | 1 }>>([])
  const [samRedo, setSamRedo] = useState<Array<{ point: [number, number]; label: 0 | 1 }>>([])
  const [samPreview, setSamPreview] = useState<number[]>([])
  const [samPreviewMode, setSamPreviewMode] = useState<'polygon' | 'pixels'>('polygon')
  const [samSimplify, setSamSimplify] = useState(0.2)
  const warmedSamModels = useRef(new Set<string>())
  const [busy, setBusy] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [exportName, setExportName] = useState('native-reviewed')
  const [datasetDisplayName, setDatasetDisplayName] = useState('')
  const [datasetVersion, setDatasetVersion] = useState('0.1.0')
  const [reviewedCount, setReviewedCount] = useState(0)
  const [splitRatios, setSplitRatios] = useState<SplitRatios>({ train: 70, val: 20, test: 10 })

  const load = async (targetPage = page, preferredFrameId?: string, preferredDetail?: AnnotationImageApiResponse) => {
    if (!taskId) {
      setImages([]); setCurrent(undefined); setTotal(0)
      return
    }
    const requestId = ++queueRequestId.current
    setQueueLoading(true)
    try {
      const next = await api.listAnnotationImages(taskId, status, targetPage, pageSize)
      if (requestId !== queueRequestId.current) return
      setImages(next.items)
      setTotal(next.total)
      setStatusCounts(next.status_counts)
      const maximumPage = Math.max(1, Math.ceil(next.total / pageSize))
      if (targetPage > maximumPage) {
        setCurrent(undefined)
        setPage(maximumPage)
        return
      }
      const selectedFrameId = next.items.some((item) => item.frame_id === preferredFrameId)
        ? preferredFrameId
        : next.items[0]?.frame_id
      if (!selectedFrameId) {
        setCurrent(undefined)
        return
      }
      if (preferredDetail?.frame_id === selectedFrameId) {
        setCurrent(preferredDetail)
        return
      }
      const detail = await api.getAnnotationImage(selectedFrameId)
      if (requestId === queueRequestId.current) setCurrent(detail)
    } finally {
      if (requestId === queueRequestId.current) setQueueLoading(false)
    }
  }

  useEffect(() => {
    if (!taskId && tasks.length) setTaskId(tasks[0].id)
  }, [taskId, tasks])
  useEffect(() => { void load(page).catch((reason) => message.error(reason.message)) }, [taskId, status, page])
  useEffect(() => {
    dispatchInteraction({ type: 'image-change', classCount: current?.classes.length ?? 0, readonly: current?.status === 'reviewed' })
    clearSmartSelect()
  }, [current?.frame_id, current?.status, current?.classes.length])

  const selectImage = async (frameId: string) => {
    const requestId = ++detailRequestId.current
    dispatchInteraction({ type: 'image-change', classCount: 0 })
    clearSmartSelect()
    try {
      const detail = await api.getAnnotationImage(frameId)
      if (requestId === detailRequestId.current) setCurrent(detail)
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '读取标注详情失败')
    }
  }

  const applyServerImage = (next: AnnotationImageApiResponse) => {
    setCurrent(next)
    setImages((items) => items.map((item) => item.frame_id === next.frame_id ? {
      ...item,
      status: next.status,
      revision: next.revision,
      shape_count: next.shapes.length,
      updated_at: next.updated_at,
    } : item))
  }

  const selectedShape = current?.shapes.find((shape) => shape.id === interaction.selectedShapeId)
  const displayNames = useMemo(() => tasks.find((task) => task.id === current?.task_id)?.class_display_names ?? {}, [current?.task_id, tasks])
  const objects = useMemo(() => buildObjectPresentation(current?.shapes ?? [], displayNames), [current?.shapes, displayNames])

  const mutate = async (operation: () => Promise<AnnotationImageApiResponse>) => {
    try {
      setBusy(true)
      const next = await operation()
      const itemStillMatches = !status || next.status === status
      const nextPage = resolveAnnotationQueuePage({ reason: 'item-updated', page, pageSize, total, itemStillMatches })
      if (nextPage !== page) {
        setCurrent(undefined)
        setPage(nextPage)
      } else {
        await load(page, itemStillMatches ? next.frame_id : undefined, itemStillMatches ? next : undefined)
      }
      return next
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : '标注操作失败'
      if (/revision|conflict|409/i.test(detail)) {
        message.warning('标注已被其他操作更新，请确认最新对象后重试。')
      } else {
        message.error(detail)
      }
      if (current) applyServerImage(await api.getAnnotationImage(current.frame_id))
      return undefined
    } finally {
      setBusy(false)
    }
  }

  const createShape = async (shapeType: 'box' | 'polygon', coordinates: number[]) => {
    if (!current) return
    const beforeIds = current.shapes.map((shape) => shape.id)
    const classId = interaction.newClassId
    const className = current.classes[classId]
    if (classId < 0 || !className) return message.warning('请先选择新建对象类别')
    const next = await mutate(() => api.createAnnotationShape(current.frame_id, { revision: current.revision, class_id: classId, class_name: className, shape_type: shapeType, coordinates, source: 'manual' }))
    const createdId = next && findCreatedShapeId(beforeIds, next.shapes.map((shape) => shape.id))
    if (createdId) dispatchInteraction({ type: 'select-shape', shapeId: createdId })
  }

  const updateShape = (shape: AnnotationShapeApiResponse, coordinates: number[]) => {
    if (!current) return
    void mutate(() => api.updateAnnotationShape(current.frame_id, shape.id, { revision: current.revision, class_id: shape.class_id, class_name: shape.class_name, shape_type: shape.shape_type, coordinates, source: shape.source }))
  }

  const saveSelectedShapeClass = async () => {
    if (!current || !selectedShape || interaction.classDraft === undefined) return
    const nextClassId = interaction.classDraft
    const next = await mutate(() => api.updateAnnotationShape(current.frame_id, selectedShape.id, { revision: current.revision, class_id: nextClassId, class_name: current.classes[nextClassId], shape_type: selectedShape.shape_type, coordinates: selectedShape.coordinates, source: selectedShape.source }))
    if (next?.shapes.some((shape) => shape.id === selectedShape.id)) dispatchInteraction({ type: 'cancel-class-edit' })
  }

  const deleteSelected = () => {
    if (!current || !selectedShape) return
    const object = objects.find((item) => item.id === selectedShape.id)
    Modal.confirm({
      title: `删除对象 #${object?.number ?? '?'}？`,
      content: `将删除“${object?.label ?? selectedShape.class_name}”。此操作无法撤销。`,
      okText: '删除对象',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const next = await mutate(() => api.deleteAnnotationShape(current.frame_id, selectedShape.id, current.revision))
        if (next) dispatchInteraction({ type: 'select-shape', shapeId: undefined })
      },
    })
  }

  const setImageStatus = (nextStatus: AnnotationStatus) => {
    if (!current) return
    void mutate(() => api.setAnnotationStatus(current.frame_id, current.revision, nextStatus))
  }

  const clearSmartSelect = () => {
    setSamPrompts([]); setSamRedo([]); setSamPreview([]); setSamPendingPoint(undefined)
  }

  const changeTool = (tool: AnnotationTool) => {
    clearSmartSelect()
    dispatchInteraction({ type: 'tool', tool })
  }

  const runSamPreview = async (prompts: Array<{ point: [number, number]; label: 0 | 1 }>, simplify = samSimplify) => {
    if (!current) return
    const messageKey = 'sam2-segmentation'
    try {
      setBusy(true)
      setSamPendingPoint(prompts[prompts.length - 1]?.point)
      message.loading({ key: messageKey, content: warmedSamModels.current.has(samModel) ? 'SAM2 正在更新分割结果…' : 'SAM2 正在加载模型并分割，首次可能需要 15–30 秒…', duration: 0 })
      const result = await api.previewAnnotationWithSam(current.frame_id, { model: samModel, positive_points: prompts.filter((item) => item.label === 1).map((item) => item.point), negative_points: prompts.filter((item) => item.label === 0).map((item) => item.point), simplify })
      warmedSamModels.current.add(samModel)
      setSamPreview(result.polygon)
      message.success({ key: messageKey, content: result.model_was_loaded ? 'SAM2 模型已加载，后续点选将直接复用' : 'SAM2 预览已更新，确认后点击 Finish', duration: 2 })
    } catch (reason) {
      message.error({ key: messageKey, content: reason instanceof Error ? reason.message : 'SAM2 分割失败', duration: 5 })
    } finally {
      setSamPendingPoint(undefined)
      setBusy(false)
    }
  }

  const samPoint = (point: [number, number]) => {
    const label: 0 | 1 = samPreview.length >= 6 && isPointInsidePolygon(point, samPreview) ? 0 : 1
    const next = [...samPrompts, { point, label }]
    setSamPrompts(next)
    setSamRedo([])
    void runSamPreview(next)
  }

  const undoSam = () => {
    if (!samPrompts.length || busy) return
    const removed = samPrompts[samPrompts.length - 1]
    const next = samPrompts.slice(0, -1)
    setSamPrompts(next); setSamRedo((items) => [removed, ...items])
    if (next.some((item) => item.label === 1)) void runSamPreview(next); else setSamPreview([])
  }

  const redoSam = () => {
    if (!samRedo.length || busy) return
    const restored = samRedo[0]
    const next = [...samPrompts, restored]
    setSamPrompts(next); setSamRedo((items) => items.slice(1)); void runSamPreview(next)
  }

  const finishSam = async () => {
    if (!current || samPreview.length < 6 || busy) return
    const classId = interaction.newClassId
    const className = current.classes[classId]
    if (classId < 0 || !className) return message.warning('请先选择新建对象类别')
    try {
      setBusy(true)
      const beforeIds = current.shapes.map((shape) => shape.id)
      const next = await api.createAnnotationShape(current.frame_id, { revision: current.revision, class_id: classId, class_name: className, shape_type: 'polygon', coordinates: samPreview, source: 'sam2' })
      await load(page, next.frame_id, next)
      const createdId = findCreatedShapeId(beforeIds, next.shapes.map((shape) => shape.id))
      clearSmartSelect()
      dispatchInteraction({ type: 'select-shape', shapeId: createdId })
      message.success('智能选择已保存，可在选择模式下拖动顶点继续修正')
    } catch (reason) { message.error(reason instanceof Error ? reason.message : '保存智能选择失败') } finally { setBusy(false) }
  }

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.matches('input, textarea, [contenteditable="true"]') || target?.closest('.ant-select, .ant-input-number')) return
      if (event.key === 'Enter') {
        if (interaction.classDraft !== undefined) void saveSelectedShapeClass()
        else if (interaction.tool === 'sam') void finishSam()
      }
      if (event.key === 'Escape') {
        if (interaction.classDraft !== undefined) {
          dispatchInteraction({ type: 'escape' })
        } else if (interaction.tool === 'sam' && (samPrompts.length || samPreview.length)) {
          clearSmartSelect()
        } else {
          dispatchInteraction({ type: 'escape' })
        }
      }
    }
    window.addEventListener('keydown', keyboard)
    return () => window.removeEventListener('keydown', keyboard)
  }, [interaction, current, selectedShape, samPreview, samPrompts, busy])

  const sync = async () => {
    if (!taskId) return message.warning('请先选择任务')
    try {
      setBusy(true)
      const result = await api.syncAnnotationImages(taskId)
      setCurrent(undefined)
      if (page !== 1) setPage(1); else await load(1)
      message.success(`已同步 ${result.synced_count} 张新图片，队列共 ${result.total_count} 张`)
    } catch (reason) { message.error(reason instanceof Error ? reason.message : '同步失败') } finally { setBusy(false) }
  }

  const exportReviewed = async () => {
    const exportTaskId = resolveAnnotationTaskId(taskId, current?.task_id)
    if (!exportTaskId) {
      message.warning('请先选择要导出的任务')
      return
    }
    try {
      setBusy(true)
      const result = await api.exportNativeAnnotations(exportTaskId, exportName)
      await api.releaseDataset(exportTaskId, result.export_id, datasetDisplayName.trim(), datasetVersion, splitRatios)
      setExportOpen(false)
      refreshDashboard()
      Modal.success({
        title: `数据集 v${datasetVersion} 已发布`,
        content: result.sample_count === 1 ? '已导出 1 张审核图片。这是单图流程测试，验证集会复用训练图，评估指标不具备参考价值。' : `已导出 ${result.sample_count} 张审核图片，可以开始训练。`,
        okText: '进入训练',
        onOk: () => onNavigate('training'),
      })
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '导出或发布失败')
    } finally { setBusy(false) }
  }

  const openExport = async () => {
    const exportTaskId = resolveAnnotationTaskId(taskId, current?.task_id)
    if (!exportTaskId) return message.warning('请先选择要导出的任务')
    setExportName(createNativeExportName())
    setDatasetDisplayName(`${exportTaskId} 数据集`)
    setExportOpen(true)
    try {
      setBusy(true)
      const [releases, reviewed] = await Promise.all([
        api.releases(),
        api.listAnnotationImages(exportTaskId, 'reviewed', 1, 1),
      ])
      setDatasetVersion(nextDatasetVersion(releases, exportTaskId))
      setReviewedCount(reviewed.total)
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '读取发布信息失败')
    } finally {
      setBusy(false)
    }
  }

  return <div className="annotation-page">
    <div className="annotation-toolbar">
      <Space wrap>
        <Button icon={<ArrowLeft size={15} />} onClick={() => onNavigate('review')}>返回数据筛选</Button>
        <Select disabled={busy} allowClear placeholder="选择任务" value={taskId} onChange={(value) => { dispatchInteraction({ type: 'image-change', classCount: 0 }); clearSmartSelect(); setTaskId(value); setPage(resolveAnnotationQueuePage({ reason: 'filter-change', page, pageSize, total })); setCurrent(undefined) }} options={tasks.map((task) => ({ value: task.id, label: `${task.id} · ${task.task_type}` }))} style={{ width: 260 }} />
        <Select disabled={busy} allowClear placeholder="全部状态" value={status} onChange={(value) => { dispatchInteraction({ type: 'image-change', classCount: 0 }); clearSmartSelect(); setStatus(value); setPage(resolveAnnotationQueuePage({ reason: 'filter-change', page, pageSize, total })); setCurrent(undefined) }} options={Object.entries(statusLabels).map(([value, label]) => ({ value, label: `${label} (${statusCounts[value as AnnotationStatus] ?? 0})` }))} style={{ width: 150 }} />
        <Button icon={<RotateCcw size={15} />} onClick={() => void sync()} loading={busy}>同步选中帧</Button>
        <Button icon={<Upload size={15} />} disabled={!resolveAnnotationTaskId(taskId, current?.task_id)} onClick={() => void openExport()}>导出已审核</Button>
      </Space>
      <Space className="annotation-tool-strip">
        <Tooltip title="选择对象"><Button disabled={!current || busy} type={interaction.tool === 'select' ? 'primary' : 'default'} icon={<MousePointer2 size={16} />} onClick={() => changeTool('select')} /></Tooltip>
        <Tooltip title="新建矩形"><Button disabled={!current || busy || current.status === 'reviewed' || current.task_type === 'segment'} type={interaction.tool === 'box' ? 'primary' : 'default'} icon={<Box size={16} />} onClick={() => changeTool('box')} /></Tooltip>
        <Tooltip title="新建多边形"><Button disabled={!current || busy || current.status === 'reviewed' || current.task_type === 'detect'} type={interaction.tool === 'polygon' ? 'primary' : 'default'} icon={<Pentagon size={16} />} onClick={() => changeTool('polygon')} /></Tooltip>
        <Tooltip title="SAM2 智能分割"><Button disabled={!current || busy || current.status === 'reviewed' || current.task_type !== 'segment'} type={interaction.tool === 'sam' ? 'primary' : 'default'} icon={<Sparkles size={16} />} onClick={() => changeTool('sam')} /></Tooltip>
      </Space>
    </div>

    <div className="annotation-workspace">
      <aside className="annotation-queue">
        <div className="annotation-pane-heading"><strong>标注队列</strong><span>{total} 张</span></div>
        <List loading={queueLoading} dataSource={images} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可标注图片" /> }} renderItem={(item) => <List.Item className={item.frame_id === current?.frame_id ? 'active' : ''} onClick={() => void selectImage(item.frame_id)}>
          <img loading="lazy" src={api.getAnnotationThumbnailUrl(item.frame_id)} alt="" />
          <div><strong>{item.frame_id}</strong><span>{item.shape_count} 个标注</span></div>
          <Tag color={item.status === 'reviewed' ? 'green' : item.status === 'annotated' ? 'blue' : 'default'}>{statusLabels[item.status]}</Tag>
        </List.Item>} />
        {total > 0 && <div className="annotation-queue-pagination"><Pagination disabled={busy} simple size="small" current={page} pageSize={pageSize} total={total} showSizeChanger={false} onChange={(nextPage) => { setCurrent(undefined); dispatchInteraction({ type: 'image-change', classCount: 0 }); clearSmartSelect(); setPage(nextPage) }} /></div>}
      </aside>

      <main className="annotation-stage-panel">
        {current ? <AnnotationCanvas image={current} imageUrl={api.getAnnotationImageUrl(current.frame_id)} tool={interaction.tool} objects={objects} selectedShapeId={interaction.selectedShapeId} disabled={current.status === 'reviewed' || busy} samPendingPoint={samPendingPoint} samPrompts={samPrompts} samPreviewPolygon={samPreview} samPreviewMode={samPreviewMode} onSelect={(shapeId) => dispatchInteraction({ type: 'select-shape', shapeId })} onCreate={(shapeType, coordinates) => void createShape(shapeType, coordinates)} onUpdate={updateShape} onSamPoint={samPoint} /> : <Empty description="选择任务并同步选中帧" />}
      </main>

      <aside className="annotation-properties">
        {current ? <AnnotationInspector
          image={current}
          displayNames={displayNames}
          interaction={interaction}
          objects={objects}
          busy={busy}
          onNewClassChange={(classId) => dispatchInteraction({ type: 'set-new-class', classId })}
          onSelectObject={(shapeId) => dispatchInteraction({ type: 'select-shape', shapeId })}
          onBeginClassEdit={(classId) => dispatchInteraction({ type: 'begin-class-edit', classId })}
          onClassDraftChange={(classId) => dispatchInteraction({ type: 'set-class-draft', classId })}
          onSaveClass={() => void saveSelectedShapeClass()}
          onCancelClassEdit={() => dispatchInteraction({ type: 'cancel-class-edit' })}
          onDeleteObject={deleteSelected}
          onStatusChange={setImageStatus}
          createControls={current.task_type === 'segment' && interaction.tool === 'sam' ? <div className="smart-select-panel">
            <div className="smart-select-title"><strong>Smart Select</strong><Button type="text" size="small" onClick={clearSmartSelect}>×</Button></div>
            <label>模型</label><Select value={samModel} onChange={(value) => { setSamModel(value); clearSmartSelect() }} options={[{ value: 'sam2_t.pt', label: 'SAM2 Tiny' }, { value: 'sam2_s.pt', label: 'SAM2 Small' }]} />
            <Segmented block value={samPreviewMode} onChange={(value) => setSamPreviewMode(value as 'polygon' | 'pixels')} options={[{ value: 'polygon', label: 'Polygon' }, { value: 'pixels', label: 'Pixels' }]} />
            <p>点击遮罩外部添加区域，点击遮罩内部排除区域。</p>
            <Space.Compact block><Button block disabled={!samPrompts.length || busy} icon={<Undo2 size={14} />} onClick={undoSam}>Undo</Button><Button block disabled={!samRedo.length || busy} icon={<Redo2 size={14} />} onClick={redoSam}>Redo</Button></Space.Compact>
            <label>Simplify</label><Slider min={0} max={1} step={0.05} value={samSimplify} onChange={setSamSimplify} onChangeComplete={(value) => { if (samPrompts.length) void runSamPreview(samPrompts, value) }} /><div className="simplify-labels"><span>精细</span><span>简洁</span></div>
            <div className="smart-select-actions"><Button danger onClick={clearSmartSelect}>清空提示点</Button><Button type="primary" disabled={samPreview.length < 6 || busy} onClick={() => void finishSam()}>保存对象 (Enter)</Button></div>
          </div> : undefined}
        /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无图片" />}
      </aside>
    </div>
    <Modal title="导出并发布 YOLO 数据集" open={exportOpen} confirmLoading={busy} okButtonProps={{ disabled: !resolveAnnotationTaskId(taskId, current?.task_id) || !exportName.trim() || !datasetDisplayName.trim() || !/^\d+\.\d+\.\d+$/.test(datasetVersion) || Boolean(validateSplitRatios(splitRatios)) }} onCancel={() => setExportOpen(false)} onOk={() => void exportReviewed()} okText="导出并发布">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Alert type="info" showIcon message={`导出任务：${resolveAnnotationTaskId(taskId, current?.task_id) ?? '未选择'}`} />
        <label>导出名称</label><Input value={exportName} onChange={(event) => setExportName(event.target.value)} placeholder="native-reviewed" />
        <label>数据集名称</label><Input maxLength={200} showCount value={datasetDisplayName} onChange={(event) => setDatasetDisplayName(event.target.value)} placeholder="例如：电梯标识分割数据集" />
        <label>数据集版本</label><Input value={datasetVersion} onChange={(event) => setDatasetVersion(event.target.value)} placeholder="0.1.0" />
        <label>数据集划分比例</label>
        <Space.Compact block>
          <InputNumber addonBefore="训练" addonAfter="%" min={0} max={100} value={splitRatios.train} onChange={(value) => setSplitRatios((current) => ({ ...current, train: value ?? 0 }))} />
          <InputNumber addonBefore="验证" addonAfter="%" min={0} max={100} value={splitRatios.val} onChange={(value) => setSplitRatios((current) => ({ ...current, val: value ?? 0 }))} />
          <InputNumber addonBefore="测试" addonAfter="%" min={0} max={100} value={splitRatios.test} onChange={(value) => setSplitRatios((current) => ({ ...current, test: value ?? 0 }))} />
        </Space.Compact>
        {validateSplitRatios(splitRatios) ? <Alert type="error" showIcon message={validateSplitRatios(splitRatios)} /> : (() => { const counts = previewSplitCounts(reviewedCount, splitRatios); return <Alert type={reviewedCount < 3 ? 'warning' : 'info'} showIcon message={`审核通过 ${reviewedCount} 张；预计训练 ${counts.train} 张 / 验证 ${counts.val} 张 / 测试 ${counts.test} 张`} description="视频帧按源视频整组划分，实际数量可能略有偏差；非零集合必须拥有独立来源。" /> })()}
      </Space>
    </Modal>
  </div>
}
