import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Form, List, message, Modal, Progress, Segmented, Select, Slider, Spin, Switch, Tag, Tooltip, Upload as AntUpload } from 'antd'
import { Download, FileImage, Images, Play, Square, Trash2, Upload, Video } from 'lucide-react'

import { api } from '../../api'
import { PageHeader } from '../../components/platform/PageHeader'
import { platformRepository } from '../../platform/repository'
import { mapInference } from '../../platform/apiPlatformRepository'
import type { InferenceMode, InferenceRun, ModelArtifact, TaskType } from '../../platform/types'
import { getInferencePreviewKind, selectInitialInferenceModel, selectModelForTask } from './inferencePresentation'

export default function InferencePage() {
  const [mode, setMode] = useState<InferenceMode>('image')
  const [task, setTask] = useState<TaskType>('detect')
  const [publishedModels, setPublishedModels] = useState<ModelArtifact[]>([])
  const [running, setRunning] = useState(false)
  const [run, setRun] = useState<InferenceRun>()
  const [history, setHistory] = useState<InferenceRun[]>([])
  const [sourceFiles, setSourceFiles] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState(0)
  const [showStructuredMasks, setShowStructuredMasks] = useState(false)
  const [form] = Form.useForm()
  const models = publishedModels.filter((model) => model.task === task)
  useEffect(() => {
    void platformRepository.listModels({ status: 'published' })
      .then((next) => {
        setPublishedModels(next)
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
      const response = await api.uploadInferenceRun({ model_version_id: values.modelId, mode, runtime: values.runtime, confidence: values.confidence }, sourceFiles, setUploadProgress)
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
    form.setFieldValue('modelId', selectModelForTask(publishedModels, nextTask))
  }

  return <div className="platform-stack">
    <PageHeader title="推理工作台" description="使用已发布且通过 PT/ONNX 一致性门禁的模型运行真实图片、批量图片和视频推理。" />
    <section className="inference-workspace">
      <div className="platform-panel inference-controls">
        <Segmented block value={mode} onChange={(value)=>{setMode(value as InferenceMode);setSourceFiles([])}} options={[{value:'image',label:'单张图片',icon:<FileImage size={15}/>},{value:'batch',label:'批量图片',icon:<Images size={15}/>},{value:'video',label:'视频文件',icon:<Video size={15}/>}]} />
        <Form form={form} layout="vertical" initialValues={{ confidence:0.25, runtime:'pt' }}>
          <Form.Item label="任务类型"><Select value={task} onChange={changeTask} options={['detect','segment'].map((value)=>({value,label:`${value.toUpperCase()} (${publishedModels.filter((model) => model.task === value).length})`}))} /></Form.Item>
          <Form.Item name="modelId" label="已发布模型" rules={[{required:true,message:'请选择已发布模型'}]}><Select placeholder={models.length ? '选择模型' : '暂无该任务的已发布模型'} options={models.map((model)=>({value:model.id,label:`${model.name} v${model.version}`}))} /></Form.Item>
          <Form.Item name="runtime" label="推理制品" rules={[{required:true}]}><Segmented block options={[{label:'PyTorch / CUDA',value:'pt'},{label:'ONNX / CPU',value:'onnx'}]} /></Form.Item>
          <Form.Item label={mode === 'batch' ? '上传图片（可多选）' : mode === 'video' ? '上传视频' : '上传图片'} required>
            <AntUpload.Dragger
              accept={mode === 'video' ? '.mp4,.avi,.mov,.mkv,.m4v' : 'image/*,.tif,.tiff'}
              multiple={mode === 'batch'}
              maxCount={mode === 'batch' ? undefined : 1}
              beforeUpload={(file) => { setSourceFiles((current) => mode === 'batch' ? [...current, file] : [file]); return false }}
              onRemove={(file) => { setSourceFiles((current) => current.filter((item) => item.name !== file.name || item.lastModified !== file.lastModified)); return true }}
              fileList={sourceFiles as any}
              disabled={running}
            >
              <p><Upload size={24} /></p>
              <p>{mode === 'batch' ? '点击或拖拽多张图片' : mode === 'video' ? '点击或拖拽一个视频' : '点击或拖拽一张图片'}</p>
            </AntUpload.Dragger>
            {running && uploadProgress > 0 && uploadProgress < 100 && <Progress percent={uploadProgress} size="small" style={{ marginTop: 12 }} />}
          </Form.Item>
          <Form.Item name="confidence" label="置信度阈值"><Slider min={0.05} max={0.95} step={0.05} marks={{0.05:'0.05',0.5:'0.50',0.95:'0.95'}} /></Form.Item>
          <Button block type="primary" icon={<Play size={16}/>} loading={running} disabled={!models.length} onClick={() => void execute()}>开始推理</Button>
        </Form>
      </div>
      <div className="platform-panel inference-preview">
        <div className="platform-panel-heading"><div><h3>结果预览</h3><p>检测明细与标注媒体来自独立推理 Runner</p></div>{run && <span><Switch size="small" checked={showStructuredMasks} onChange={setShowStructuredMasks} disabled={run.mode === 'video'} /> <small>结构化蒙版</small> <Tag color={run.status === 'completed' ? 'green' : ['queued','running'].includes(run.status) ? 'blue' : 'red'}>{run.status}</Tag>{['queued','running'].includes(run.status) && <Button danger size="small" icon={<Square size={13}/>} onClick={()=>void cancel(run)}>取消</Button>}</span>}</div>
        {running || (run && ['queued','running'].includes(run.status)) ? <Spin tip="后台推理中，可离开页面后从历史恢复"><div style={{height:240}} /></Spin> : !run ? <Empty image={<FileImage size={52}/>} description="提交推理后在此查看真实结果" /> : run.status !== 'completed' ? <Alert type="error" showIcon message={`推理${run.status}`} description="请检查输入路径、模型制品和 Runner 日志。" /> : <List className="inference-result-list" dataSource={run.results} locale={{emptyText:'推理完成，当前阈值下未产生结果项'}} renderItem={(item) => {
          const previewKind = getInferencePreviewKind(run.mode, item.mediaPath)
          const mediaUrl = item.mediaPath ? api.getArtifactUrl(item.mediaPath) : undefined
          const polygons = item.detectionItems.filter((detection) => detection.polygon && detection.polygon.length >= 6)
          const sourceUrl = api.getArtifactUrl(item.sourceName)
          return <List.Item className="inference-result-item" actions={mediaUrl ? [<Button key="download" icon={<Download size={14}/>} href={mediaUrl} target="_blank">打开标注产物</Button>] : []}>
            <div className="inference-result-content">
              <div className="inference-result-media">
                {previewKind === 'image' && mediaUrl && (showStructuredMasks && polygons.length ? <div className="inference-image-stage">
                  <img src={sourceUrl} alt={`${item.sourceName} 原图`} loading="lazy" />
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="结构化分割蒙版">
                    {polygons.map((detection, index) => <polygon key={`${detection.classId}-${index}`} points={detection.polygon!.reduce<string[]>((points, value, pointIndex) => pointIndex % 2 === 0 ? [...points, `${value * 100},${detection.polygon![pointIndex + 1] * 100}`] : points, []).join(' ')} />)}
                  </svg>
                </div> : <img src={mediaUrl} alt={`${item.sourceName} 推理结果预览`} loading="lazy" />)}
                {previewKind === 'video' && mediaUrl && <video src={mediaUrl} controls preload="metadata" playsInline />}
                {previewKind === 'none' && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次结果没有可预览媒体" />}
              </div>
              <div className="inference-result-meta">
                <strong>{item.sourceName.split(/[\\/]/).pop() || item.sourceName}</strong>
                <span>{item.summary} · 推理 {item.durationMs.toFixed(1)} ms</span>
                <Tooltip title={item.sourceName}><code>{item.sourceName}</code></Tooltip>
              </div>
            </div>
          </List.Item>
        }} />}
      </div>
    </section>
    <section className="platform-panel"><div className="platform-panel-heading"><div><h3>推理历史</h3><p>已持久化的图片、批量图片和视频推理记录</p></div></div><List dataSource={history} locale={{ emptyText: '暂无推理历史' }} renderItem={(item)=><List.Item actions={[<Button key="open" type="link" onClick={()=>setRun(item)}>查看</Button>,...(['queued','running'].includes(item.status)?[<Button key="cancel" danger type="link" onClick={()=>void cancel(item)}>取消</Button>]:[<Tooltip key="delete-record" title="保留输出文件"><Button danger type="text" icon={<Trash2 size={14}/>} onClick={()=>deleteHistory(item,false)} /></Tooltip>,<Tooltip key="delete-files" title="删除记录与输出"><Button danger type="text" icon={<Trash2 size={14}/>} onClick={()=>deleteHistory(item,true)} /></Tooltip>])]}><List.Item.Meta title={`${item.mode.toUpperCase()} · ${item.runtime.toUpperCase()}`} description={`${item.id} · ${new Date(item.createdAt).toLocaleString('zh-CN')}`} /><Tag color={item.status==='completed'?'green':['queued','running'].includes(item.status)?'blue':'red'}>{item.status}</Tag></List.Item>} /></section>
  </div>
}
