import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Form, Input, List, message, Modal, Progress, Segmented, Select, Slider, Spin, Tag, Tooltip, Upload as AntUpload } from 'antd'
import { FileImage, Images, Plus, Play, Square, Trash2, Upload, Video } from 'lucide-react'

import { api } from '../../api'
import type { ImportedModelApiResponse } from '../../api'
import { PageHeader } from '../../components/platform/PageHeader'
import { platformRepository } from '../../platform/repository'
import { mapInference } from '../../platform/apiPlatformRepository'
import type { InferenceMode, InferenceRun, ModelArtifact, TaskType } from '../../platform/types'
import { InferenceResultViewer } from './InferenceResultViewer'
import { selectInitialInferenceModel, selectModelForTask } from './inferencePresentation'

export default function InferencePage() {
  const [sourceKind, setSourceKind] = useState<'published' | 'candidate' | 'imported'>('published')
  const [mode, setMode] = useState<InferenceMode>('image')
  const [task, setTask] = useState<TaskType>('detect')
  const [allModels, setAllModels] = useState<ModelArtifact[]>([])
  const [importedModels, setImportedModels] = useState<ImportedModelApiResponse[]>([])
  const [modelFile, setModelFile] = useState<File | undefined>(undefined)
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState<InferenceRun>()
  const [history, setHistory] = useState<InferenceRun[]>([])
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState(0)
  const [showStructuredMasks, setShowStructuredMasks] = useState(false)
  const [form] = Form.useForm()
  const [importForm] = Form.useForm()
  const confidence = Form.useWatch('confidence', form) ?? 0.25
  const models = allModels.filter((model) => model.task === task && (sourceKind === 'published' ? model.status === 'published' : ['candidate', 'blocked'].includes(model.status)))
  const imported = importedModels.filter((model) => model.task_type === task)
  const reloadModels = () => Promise.all([platformRepository.listModels({}), api.listImportedModels()]).then(([registered, uploads]) => { setAllModels(registered); setImportedModels(uploads) })
  useEffect(() => {
    void reloadModels()
      .then(() => platformRepository.listModels({ status: 'published' }))
      .then((next) => {
        const selection = selectInitialInferenceModel(next, 'detect')
        setTask(selection.task)
        form.setFieldValue('modelId', selection.modelId)
      })
      .catch((error) => message.error(error.message))
  }, [form])
  const loadHistory = () => api.listInferenceRuns().then((items) => setHistory(items.map(mapInference)))
  useEffect(() => { void loadHistory().catch((error) => message.error(error.message)) }, [])
  useEffect(() => {
    const active = history.filter((item) => ['queued', 'running'].includes(item.status))
    if (!active.length) return
    const timer = window.setInterval(() => {
      void Promise.all(active.map((item) => api.refreshInferenceRun(item.id)))
        .then(async (items) => {
          const mapped = items.map(mapInference)
          if (run) setRun(mapped.find((item) => item.id === run.id) ?? run)
          await loadHistory()
        })
        .catch((error) => message.error(error instanceof Error ? error.message : '刷新推理进度失败'))
    }, 1500)
    return () => window.clearInterval(timer)
  }, [history, run])

  const execute = async () => {
    try {
      const values = await form.validateFields()
      if (!sourceFiles.length) return message.warning(mode === 'video' ? '请选择一个视频文件' : '请选择图片文件')
      setRunning(true); setRun(undefined)
      setUploadProgress(0)
      const response = await api.uploadInferenceRun(sourceKind === 'imported'
        ? { imported_model_id: values.modelId, mode, runtime: values.runtime, confidence: values.confidence }
        : { model_version_id: values.modelId, mode, runtime: values.runtime, confidence: values.confidence }, sourceFiles, setUploadProgress)
      const next = { ...mapInference(response), task }
      setRun(next)
      setSourceFiles([])
      await loadHistory()
      next.status === 'completed' ? message.success('推理完成') : message.info('推理任务已提交到后台')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '推理请求失败')
    } finally { setRunning(false); setUploadProgress(0) }
  }

  const deleteHistory = (item: InferenceRun, deleteArtifacts: boolean) => Modal.confirm({ title: deleteArtifacts ? '删除推理记录和输出？' : '删除推理记录？', content: deleteArtifacts ? '标注媒体和结构化结果会被永久删除。' : '仅删除历史记录，输出文件保留。', okButtonProps: { danger: true }, okText: deleteArtifacts ? '永久删除' : '删除记录', onOk: async () => { try { await api.deleteInferenceRun(item.id, deleteArtifacts); if (run?.id === item.id) setRun(undefined); await loadHistory(); message.success('推理历史已删除') } catch (error) { message.error(error instanceof Error ? error.message : '删除推理历史失败'); throw error } } })
  const cancel = async (item: InferenceRun) => { try { const next = mapInference(await api.cancelInferenceRun(item.id)); if (run?.id === item.id) setRun(next); await loadHistory(); message.info('已请求取消推理') } catch (error) { message.error(error instanceof Error ? error.message : '取消推理失败') } }

  const changeTask = (nextTask: TaskType) => {
    setTask(nextTask)
    const next = sourceKind === 'imported'
      ? importedModels.find((item) => item.task_type === nextTask)
      : allModels.find((item) => item.task === nextTask && (sourceKind === 'published' ? item.status === 'published' : ['candidate', 'blocked'].includes(item.status)))
    form.setFieldsValue({ modelId: next?.id, runtime: sourceKind === 'imported' && next && 'artifact_format' in next ? next.artifact_format : 'pt' })
  }

  const changeSourceKind = (kind: 'published' | 'candidate' | 'imported') => {
    setSourceKind(kind)
    const next = kind === 'imported' ? importedModels.find((item) => item.task_type === task) : allModels.find((item) => item.task === task && (kind === 'published' ? item.status === 'published' : ['candidate', 'blocked'].includes(item.status)))
    form.setFieldsValue({ modelId: next?.id, runtime: kind === 'imported' && next && 'artifact_format' in next ? next.artifact_format : 'pt' })
  }

  const importModel = async () => {
    const values = await importForm.validateFields()
    const name = String(values.name ?? '').trim()
    if (!modelFile) return message.warning('请选择 .pt 或 .onnx 文件')
    if (task !== 'detect' && task !== 'segment') return message.warning('当前仅支持检测和分割模型')
    try { setImporting(true); const created = await api.uploadImportedModel({ name, task_type: task, class_names: [] }, modelFile); await reloadModels(); setSourceKind('imported'); form.setFieldsValue({ modelId: created.id, runtime: created.artifact_format }); setImportOpen(false); setModelFile(undefined); importForm.resetFields(); message.success('测试模型已导入并自动选中') }
    catch (error) { message.error(error instanceof Error ? error.message : '模型导入失败') } finally { setImporting(false) }
  }

  return <div className="platform-stack">
    <PageHeader title="推理工作台" description="可使用已发布模型，也可临时验证候选模型或已导入的 PT/ONNX 文件。" />
    <section className="inference-workspace">
      <div className="platform-panel inference-controls">
        <Segmented block value={mode} onChange={(value)=>{setMode(value as InferenceMode);setSourceFiles([])}} options={[{value:'image',label:'单张图片',icon:<FileImage size={15}/>},{value:'batch',label:'批量图片',icon:<Images size={15}/>},{value:'video',label:'视频文件',icon:<Video size={15}/>}]} />
        <Form form={form} layout="vertical" initialValues={{ confidence:0.25, runtime:'pt' }}>
          <section className="inference-control-section">
            <div className="inference-control-heading"><strong>模型配置</strong><span>选择模型来源和任务类型</span></div>
            <Form.Item label="模型来源"><Segmented block value={sourceKind} onChange={(value) => changeSourceKind(value as typeof sourceKind)} options={[{ value: 'published', label: '已发布' }, { value: 'candidate', label: '候选 / 阻断' }, { value: 'imported', label: '导入模型' }]} /></Form.Item>
            {sourceKind !== 'published' && <Alert className="inference-test-notice" showIcon type="warning" message="测试模型：结果仅用于验证，不代表正式发布结论。" />}
            <Form.Item label="任务类型"><Segmented block value={task} onChange={(value) => changeTask(value as TaskType)} options={[{ value: 'detect', label: '目标检测' }, { value: 'segment', label: '实例分割' }]} /></Form.Item>
            <div className="inference-model-picker-row">
              <Form.Item name="modelId" label={sourceKind === 'published' ? '已发布模型' : sourceKind === 'candidate' ? '候选或阻断模型' : '已导入测试模型'} rules={[{required:true,message:'请选择模型'}]}><Select placeholder="选择一个模型" onChange={(id) => { const item = importedModels.find((model) => model.id === id); if (item) form.setFieldValue('runtime', item.artifact_format) }} options={(sourceKind === 'imported' ? imported.map((model)=>({value:model.id,label:`${model.name} · ${model.artifact_format.toUpperCase()}`})) : models.map((model)=>({value:model.id,label:`${model.name} v${model.version} · ${model.status}`})))} /></Form.Item>
              {sourceKind === 'imported' && <Button icon={<Plus size={15}/>} onClick={() => setImportOpen(true)}>导入新模型</Button>}
            </div>
          </section>
          <section className="inference-control-section">
            <div className="inference-control-heading"><strong>运行配置</strong><span>PT 使用 CUDA，ONNX 使用 CPU</span></div>
            <Form.Item name="runtime" label="推理制品" rules={[{required:true}]}><Segmented block options={[{label:'PyTorch / CUDA',value:'pt'},{label:'ONNX / CPU',value:'onnx'}]} /></Form.Item>
          </section>
          <section className="inference-control-section">
            <div className="inference-control-heading"><strong>推理素材</strong><span className="inference-file-summary">已选择 {sourceFiles.length} 个文件</span></div>
            <Form.Item label={mode === 'batch' ? '上传图片（可多选）' : mode === 'video' ? '上传视频' : '上传图片'} required>
              <AntUpload.Dragger accept={mode === 'video' ? '.mp4,.avi,.mov,.mkv,.m4v' : 'image/*,.tif,.tiff'} multiple={mode === 'batch'} maxCount={mode === 'batch' ? undefined : 1} beforeUpload={(file) => { setSourceFiles((current) => mode === 'batch' ? [...current, file] : [file]); return false }} onRemove={(file) => { setSourceFiles((current) => current.filter((item) => item.name !== file.name || item.lastModified !== file.lastModified)); return true }} fileList={sourceFiles as any} disabled={running}>
                <p><Upload size={22} /></p><p>{mode === 'batch' ? '点击或拖拽多张图片' : mode === 'video' ? '点击或拖拽一个视频' : '点击或拖拽一张图片'}</p>
              </AntUpload.Dragger>
              {running && uploadProgress > 0 && uploadProgress < 100 && <Progress percent={uploadProgress} size="small" style={{ marginTop: 12 }} />}
            </Form.Item>
          </section>
          <section className="inference-control-section">
            <div className="inference-confidence-heading"><div><strong>置信度阈值</strong><span>低阈值偏召回，高阈值偏精确</span></div><output className="inference-confidence-value">{Number(confidence).toFixed(2)}</output></div>
            <Form.Item name="confidence"><Slider min={0.05} max={0.95} step={0.05} marks={{0.05:'低',0.5:'平衡',0.95:'高'}} /></Form.Item>
          </section>
          <div className="inference-submit-bar"><Button block type="primary" icon={<Play size={16}/>} loading={running} disabled={sourceKind === 'imported' ? !imported.length : !models.length} onClick={() => void execute()}>开始推理</Button></div>
        </Form>
      </div>
      <div className="platform-panel inference-preview">
        <div className="platform-panel-heading"><div><h3>结果预览</h3><p>检测明细与标注媒体来自独立推理 Runner</p></div>{run && <span><Tag color={run.status === 'completed' ? 'green' : ['queued','running'].includes(run.status) ? 'blue' : 'red'}>{run.status}</Tag>{['queued','running'].includes(run.status) && <Button danger size="small" icon={<Square size={13}/>} onClick={()=>void cancel(run)}>取消</Button>}</span>}</div>
        {running || (run && ['queued','running'].includes(run.status)) ? <Spin tip="后台推理中，可离开页面后从历史恢复"><div style={{height:240}} /></Spin> : !run ? <Empty image={<FileImage size={52}/>} description="提交推理后在此查看真实结果" /> : run.status !== 'completed' ? <Alert type="error" showIcon message={`推理${run.status}`} description="请检查输入路径、模型制品和 Runner 日志。" /> : <InferenceResultViewer run={run} showStructuredMasks={showStructuredMasks} onStructuredMasksChange={setShowStructuredMasks} />}
      </div>
    </section>
    <Modal className="inference-import-modal" title="导入新模型" open={importOpen} okText="上传并纳入测试" cancelText="取消" confirmLoading={importing} okButtonProps={{ disabled: !modelFile }} onOk={() => void importModel()} onCancel={() => { if (!importing) setImportOpen(false) }} destroyOnHidden>
      <p className="inference-import-hint">导入当前 {task.toUpperCase()} 任务使用的 .pt 或 .onnx 模型。导入成功后将自动选中。</p>
      <Form form={importForm} layout="vertical" preserve={false}>
        <Form.Item name="name" label="模型名称" rules={[{ required: true, whitespace: true, message: '请输入模型名称' }]}><Input placeholder="例如：机场设备分割 v2" /></Form.Item>
        <Form.Item label="模型文件" required><AntUpload accept=".pt,.onnx" maxCount={1} beforeUpload={(file) => { setModelFile(file); return false }} onRemove={() => { setModelFile(undefined); return true }} fileList={modelFile ? [modelFile as any] : []}><Button icon={<Upload size={15}/>}>选择 .pt / .onnx</Button></AntUpload></Form.Item>
      </Form>
    </Modal>
    <section className="platform-panel"><div className="platform-panel-heading"><div><h3>推理历史</h3><p>已持久化的图片、批量图片和视频推理记录</p></div></div><List dataSource={history} locale={{ emptyText: '暂无推理历史' }} renderItem={(item)=><List.Item actions={[<Button key="open" type="link" onClick={()=>setRun(item)}>查看</Button>,...(['queued','running'].includes(item.status)?[<Button key="cancel" danger type="link" onClick={()=>void cancel(item)}>取消</Button>]:[<Tooltip key="delete-record" title="保留输出文件"><Button danger type="text" icon={<Trash2 size={14}/>} onClick={()=>deleteHistory(item,false)} /></Tooltip>,<Tooltip key="delete-files" title="删除记录与输出"><Button danger type="text" icon={<Trash2 size={14}/>} onClick={()=>deleteHistory(item,true)} /></Tooltip>])]}><List.Item.Meta title={`${item.mode.toUpperCase()} · ${item.runtime.toUpperCase()}`} description={`${item.id} · ${new Date(item.createdAt).toLocaleString('zh-CN')}`} /><Tag color={item.status==='completed'?'green':['queued','running'].includes(item.status)?'blue':'red'}>{item.status}</Tag></List.Item>} /></section>
  </div>
}
