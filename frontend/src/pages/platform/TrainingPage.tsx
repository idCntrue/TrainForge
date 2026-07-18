import { useCallback, useEffect, useState } from 'react'
import { Alert, AutoComplete, Button, Collapse, Drawer, Dropdown, Form, Input, InputNumber, message, Modal, Progress, Segmented, Select, Space, Spin, Table, Tabs, Tooltip, Upload as AntUpload } from 'antd'
import { Box, MoreHorizontal, Plus, RefreshCw, Square, Upload } from 'lucide-react'

import { ApiError, api, type TrainingRunDetailsApiResponse, type TrainingStorageErrorDetail } from '../../api'
import { PageHeader } from '../../components/platform/PageHeader'
import { StatusTag } from '../../components/platform/StatusTag'
import { phaseLabel, statusLabel } from '../../components/platform/statusPresentation'
import { TaskTag } from '../../components/platform/TaskTag'
import { platformRepository } from '../../platform/repository'
import { mapTrainingRun } from '../../platform/apiTrainingRepository'
import type { CreateTrainingRunInput, TaskType, TrainingRun, TrainingStatus } from '../../platform/types'
import { formatClassLabel } from '../annotation/classLabels'
import { formatDatasetReleaseLabel, resolveDatasetReleaseLabel } from '../datasets/datasetReleasePresentation'
import { TrainingOverviewTab } from './training/TrainingOverviewTab'
import { TrainingChartsTab } from './training/TrainingChartsTab'
import { TrainingResultsTab } from './training/TrainingResultsTab'
import { TrainingArtifactsTab } from './training/TrainingArtifactsTab'
import { trainingFormInitialValues } from './training/trainingFormDefaults'
import { cpuTrainingPolicy, normalizeCpuTrainingValues } from './training/trainingResourcePolicy'
import { createRequestId } from '../../requestId'
import { MobileRecordCard } from '../../components/mobile/MobileRecordCard'
import { useMobileViewport } from '../../responsive/useMobileViewport'

const taskOptions = ['detect', 'segment'].map((value) => ({ value, label: value.toUpperCase() }))
const statusOptions = ['queued', 'running', 'evaluating', 'exporting', 'verifying', 'completed', 'failed', 'cancelled', 'interrupted'].map((value) => ({ value, label: statusLabel(value) }))
const activeStatuses: TrainingStatus[] = ['running', 'evaluating', 'exporting', 'verifying']
const modelPresets = {
  detect: ['yolov8n.pt', 'yolov8s.pt', 'yolo11n.pt', 'yolo11s.pt', 'yolo26n.pt', 'yolo26s.pt'],
  segment: ['yolov8n-seg.pt', 'yolov8s-seg.pt', 'yolo11n-seg.pt', 'yolo11s-seg.pt', 'yolo26n-seg.pt', 'yolo26s-seg.pt'],
}

function isTrainingStorageError(detail: unknown): detail is TrainingStorageErrorDetail {
  return Boolean(detail && typeof detail === 'object' && (detail as { code?: unknown }).code === 'insufficient_training_storage')
}

export default function TrainingPage() {
  const isMobile = useMobileViewport()
  const [runs, setRuns] = useState<TrainingRun[]>([])
  const [loading, setLoading] = useState(true)
  const [task, setTask] = useState<TaskType>()
  const [status, setStatus] = useState<TrainingStatus>()
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState<TrainingRun>()
  const [registerRun, setRegisterRun] = useState<TrainingRun>()
  const [releases, setReleases] = useState<Awaited<ReturnType<typeof api.releases>>>([])
  const [tasks, setTasks] = useState<Awaited<ReturnType<typeof api.tasks>>>([])
  const [details, setDetails] = useState<TrainingRunDetailsApiResponse>()
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [useCustomWeight, setUseCustomWeight] = useState(false)
  const [customWeightFile, setCustomWeightFile] = useState<File | null>(null)
  const [weightUploadProgress, setWeightUploadProgress] = useState(0)
  const [recoveryPending, setRecoveryPending] = useState(false)
  const [storageFailure, setStorageFailure] = useState<TrainingStorageErrorDetail>()
  const [form] = Form.useForm<CreateTrainingRunInput>()
  const [modelForm] = Form.useForm<{ name: string; version: string }>()
  const selectedClasses = Form.useWatch('selectedClasses', form) ?? []
  const activeTask = Form.useWatch('task', form) ?? 'detect'
  const activeDevice = Form.useWatch('device', form) ?? 'cpu'
  const activePreset = Form.useWatch('presetId', form) ?? 'cpu-balanced'
  const activeCpuPolicy = cpuTrainingPolicy(activeTask)
  const datasetOptions = releases.map((release) => ({ value: release.id, label: formatDatasetReleaseLabel(release) }))

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const nextRuns = await platformRepository.listTrainingRuns({ task, status })
      setRuns(nextRuns)
      setSelected((current) => current ? nextRuns.find((run) => run.id === current.id) ?? current : undefined)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载训练运行失败')
    } finally {
      setLoading(false)
    }
  }, [task, status])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    void Promise.all([api.releases(), api.tasks()])
      .then(([nextReleases, nextTasks]) => { setReleases(nextReleases.filter((release) => release.status === 'published')); setTasks(nextTasks) })
      .catch((error) => message.error(error instanceof Error ? error.message : '加载数据集版本失败'))
  }, [])
  useEffect(() => {
    const activeRuns = runs.filter((run) => activeStatuses.includes(run.status))
    if (activeRuns.length === 0) return
    const timer = window.setInterval(() => {
      void Promise.all(activeRuns.map((run) => platformRepository.refreshTrainingRun(run.id)))
        .then(() => load())
        .catch((error) => message.error(error instanceof Error ? error.message : '刷新训练进度失败'))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [load, runs])
  useEffect(() => {
    if (!selected) { setDetails(undefined); return }
    setDetailsLoading(true)
    void api.getTrainingRunDetails(selected.id)
      .then(setDetails)
      .catch((error) => message.error(error instanceof Error ? error.message : '加载训练详情失败'))
      .finally(() => setDetailsLoading(false))
  }, [selected?.id, selected?.epoch, selected?.status, selected?.progress])

  const createRun = async () => {
    try {
      const values = await form.validateFields()
      if (useCustomWeight && !customWeightFile) return message.warning('请选择一个 .pt 权重文件')
      const created = useCustomWeight && customWeightFile
        ? mapTrainingRun(await api.createTrainingRunWithWeight({
          name: values.name,
          task_type: values.task,
          dataset_release_id: values.datasetReleaseId,
          base_model: '',
          epochs: values.epochs,
          batch: values.batch,
          image_size: values.imageSize,
          device: values.device,
          selected_classes: values.selectedClasses ?? [],
          class_aliases: values.classAliases ?? {},
        }, customWeightFile, setWeightUploadProgress))
        : await platformRepository.createTrainingRun(values)
      message.success(`训练 ${created.name} 已启动`)
      setStorageFailure(undefined)
      setCreateOpen(false); form.resetFields(); setCustomWeightFile(null); setUseCustomWeight(false); await load(); setSelected(created)
    } catch (error) {
      if (error instanceof ApiError && isTrainingStorageError(error.detail)) setStorageFailure(error.detail)
      message.error(error instanceof Error ? error.message : '创建训练失败')
    } finally {
      setWeightUploadProgress(0)
    }
  }
  const resetCreateDrawer = () => {
    form.resetFields()
    setUseCustomWeight(false)
    setCustomWeightFile(null)
    setWeightUploadProgress(0)
  }
  const openCreateDrawer = () => {
    resetCreateDrawer()
    setStorageFailure(undefined)
    setCreateOpen(true)
  }
  const closeCreateDrawer = () => {
    setCreateOpen(false)
    resetCreateDrawer()
  }
  const cancelRun = async (run: TrainingRun) => {
    try {
      const next = await platformRepository.cancelTrainingRun(run.id)
      message.info('训练运行已取消'); setSelected(next); await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '取消训练失败')
    }
  }
  const deleteRun = (run: TrainingRun, deleteArtifacts: boolean, cascade = false) => {
    Modal.confirm({
      title: cascade ? '级联删除训练及全部下游？' : deleteArtifacts ? '删除训练记录和产物？' : '删除训练记录？',
      content: cascade ? '将永久删除该训练、由它注册的模型、相关推理历史及全部产物。此操作不可恢复。' : deleteArtifacts ? '训练目录、权重和日志会被永久删除。已被模型引用的训练不可删除。' : '仅删除数据库记录，训练目录和权重仍会保留。',
      okText: cascade ? '确认级联删除' : deleteArtifacts ? '永久删除' : '删除记录',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await platformRepository.deleteTrainingRun(run.id, deleteArtifacts, cascade)
          setSelected(undefined)
          await load()
          message.success(cascade ? '训练及全部下游已删除' : deleteArtifacts ? '训练记录和产物已删除' : '训练记录已删除，产物已保留')
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除训练失败')
          throw error
        }
      },
    })
  }
  const registerModel = async () => {
    if (!registerRun) return
    try {
      const values = await modelForm.validateFields()
      await api.createModelVersion({ training_run_id: registerRun.id, name: values.name, version: values.version })
      setRegisterRun(undefined)
      modelForm.resetFields()
      message.success('候选模型已注册，可前往模型中心执行门禁和发布')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '注册候选模型失败')
    }
  }
  const recoverRun = async (mode: 'safe' | 'evaluation') => {
    if (!selected || recoveryPending) return
    setRecoveryPending(true)
    try {
      const response = mode === 'safe'
        ? await api.retryTrainingRun(selected.id, { strategy: 'safe', request_id: createRequestId() })
        : await api.recoverTrainingEvaluation(selected.id)
      const child = mapTrainingRun(response)
      message.success(mode === 'safe' ? '已创建安全重试任务' : '已创建独立评估恢复任务')
      await load()
      setSelected(child)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建恢复任务失败')
    } finally {
      setRecoveryPending(false)
    }
  }
  const selectDataset = (releaseId: string) => {
    const release = releases.find((item) => item.id === releaseId)
    const datasetTask = tasks.find((item) => item.id === release?.task_id)
    if (datasetTask) {
      const resourceValues = form.getFieldValue('device') === 'cpu'
        ? normalizeCpuTrainingValues(datasetTask.task_type, {
          batch: form.getFieldValue('batch'),
          imageSize: form.getFieldValue('imageSize'),
        })
        : {}
      form.setFieldsValue({ task: datasetTask.task_type, selectedClasses: datasetTask.classes, classAliases: {}, ...resourceValues })
    }
  }

  return <div className="platform-stack">
    <PageHeader title="训练运行" description="创建、观察和停止本地 Ultralytics 训练任务。" actions={<Space><Button icon={<RefreshCw size={16} />} onClick={() => void load()}>刷新</Button><Button type="primary" icon={<Plus size={16} />} onClick={openCreateDrawer}>创建训练</Button></Space>} />
    <div className="platform-filterbar"><Select allowClear placeholder="全部任务" options={taskOptions} value={task} onChange={setTask} /><Select allowClear placeholder="全部状态" options={statusOptions} value={status} onChange={setStatus} /></div>
    <section className="platform-panel">{isMobile ? <div className="mobile-record-list">
      {runs.map((run) => <MobileRecordCard
        key={run.id}
        title={run.name}
        subtitle={resolveDatasetReleaseLabel(run.datasetReleaseId, releases)}
        status={<StatusTag status={run.status} />}
        progress={<Progress percent={run.progress} size="small" />}
        metadata={[[phaseLabel(run.phase), `${run.epoch} / ${run.epochs} Epoch`], ['Task', <TaskTag task={run.task} />]]}
        metric={`${run.metrics.primaryLabel} ${run.metrics.primary == null ? '--' : run.metrics.primary.toFixed(3)}`}
        onClick={() => setSelected(run)}
      />)}
      {!loading && runs.length === 0 && <div className="mobile-empty-state">暂无训练运行</div>}
    </div> : <Table loading={loading} rowKey="id" dataSource={runs} onRow={(run) => ({ onClick: () => setSelected(run) })} columns={[
      { title: '运行', dataIndex: 'name', render: (name, run) => <div className="table-primary"><strong>{name}</strong><span>{resolveDatasetReleaseLabel(run.datasetReleaseId, releases)}</span></div> },
      { title: '任务', dataIndex: 'task', render: (value) => <TaskTag task={value} /> }, { title: '状态', dataIndex: 'status', render: (value) => <StatusTag status={value} /> },
      { title: '进度', dataIndex: 'progress', width: 210, render: (value, run) => <div><Progress percent={value} size="small" /><small>{phaseLabel(run.phase)} · 第 {run.epoch}/{run.epochs} 轮</small></div> },
      { title: '核心指标', render: (_, run) => `${run.metrics.primaryLabel} ${run.metrics.primary == null ? '--' : run.metrics.primary.toFixed(3)}` }, { title: '创建时间', dataIndex: 'createdAt' },
    ]} />}</section>
    <Drawer className="mobile-fullscreen-drawer" width={isMobile ? '100%' : 560} title="创建训练运行" open={createOpen} onClose={closeCreateDrawer} extra={<Button type="primary" onClick={() => void createRun()}>加入队列</Button>}>
      <Form form={form} layout="vertical" initialValues={trainingFormInitialValues}>
        <Form.Item name="name" label="运行名称" rules={[{ required: true }]}><Input placeholder="例如：门板缺陷检测 v4" /></Form.Item>
        <div className="form-grid"><Form.Item name="task" label="任务类型" rules={[{ required: true }]}><Select disabled options={taskOptions} /></Form.Item><Form.Item name="datasetReleaseId" label="数据集版本" rules={[{ required: true }]}><Select popupMatchSelectWidth={520} options={datasetOptions} onChange={selectDataset} /></Form.Item></div>
        <Form.Item name="selectedClasses" label="训练 Class" rules={[{ required: true, message: '至少选择一个已标注 class' }]}><Select mode="multiple" placeholder="选择本次训练使用的 class" options={(() => { const selectedTask = tasks.find((item) => item.task_type === form.getFieldValue('task')); return (selectedTask?.classes ?? []).map((value) => ({ value, label: formatClassLabel(value, selectedTask?.class_display_names) })) })()} /></Form.Item>
        {selectedClasses.length > 0 && <><Alert type="info" showIcon message="类别别名仅用于模型和推理结果展示，不会修改数据集标签、Class ID 或训练逻辑；不需要时可留空。" /><div className="class-alias-grid">{selectedClasses.map((className) => <Form.Item key={className} name={['classAliases', className]} label={`${className} 别名`}><Input placeholder="可选，不填则保持原名" /></Form.Item>)}</div></>}
        <Form.Item label="基础权重来源"><Segmented block value={useCustomWeight ? 'custom' : 'preset'} onChange={(value) => { setUseCustomWeight(value === 'custom'); setCustomWeightFile(null) }} options={[{ label: '官方 YOLO 预设', value: 'preset' }, { label: '上传自定义 .pt', value: 'custom' }]} /></Form.Item>
        {!useCustomWeight ? <Form.Item name="baseModel" label="官方基础模型" rules={[{ required: true, message: '请选择官方基础模型' }]}><AutoComplete allowClear options={modelPresets[(form.getFieldValue('task') as 'detect'|'segment') ?? 'detect'].map((value) => ({ value }))} placeholder="请选择 YOLOv8 / YOLO11 / YOLO26" /></Form.Item> : <Form.Item label="自定义 PyTorch 权重" required>
          <AntUpload.Dragger accept=".pt" maxCount={1} beforeUpload={(file) => { setCustomWeightFile(file); return false }} onRemove={() => { setCustomWeightFile(null); return true }} fileList={customWeightFile ? [customWeightFile as any] : []}>
            <p><Upload size={24} /></p><p>点击或拖拽一个 .pt 权重文件</p>
          </AntUpload.Dragger>
          {weightUploadProgress > 0 && weightUploadProgress < 100 && <Progress percent={weightUploadProgress} size="small" style={{ marginTop: 12 }} />}
        </Form.Item>}
        {activeDevice === 'cpu' && <Alert type="warning" showIcon message="CPU 安全模式" description={`当前任务 Batch 上限 ${activeCpuPolicy.maxBatch}，图像尺寸上限 ${activeCpuPolicy.maxImageSize}。训练进程会限制线程和内存，避免占满服务器。`} />}
        {storageFailure && <Alert
          type="error"
          showIcon
          closable
          onClose={() => setStorageFailure(undefined)}
          message="训练磁盘空间不足"
          description={<span>{storageFailure.message}。请先清理 Docker 旧镜像、构建缓存或历史训练产物，再重新加入队列；详细命令见帮助中心的“云端部署与磁盘清理”。</span>}
        />}
        <Form.Item name="presetId" label="训练方案"><Segmented block options={[
          { label: '流程验证', value: 'smoke' },
          { label: 'CPU 均衡训练', value: 'cpu-balanced' },
          { label: 'GPU 高质量训练', value: 'gpu-quality', disabled: activeDevice === 'cpu' },
          { label: '自定义', value: 'custom' },
        ]} /></Form.Item>
        <Alert type="info" showIcon message={activePreset === 'smoke' ? '10 Epoch · 320px · Batch 1，适合验证全流程' : activePreset === 'cpu-balanced' ? '150 Epoch · 640px · 检测 Batch 2 / 分割 Batch 1' : activePreset === 'gpu-quality' ? '200 Epoch · 640px · Batch 8，需要 CUDA' : '高级参数仍受服务器资源上限约束'} />
        <div className="form-grid">
          {activePreset === 'custom' && <><Form.Item name="epochs" label="训练轮数（Epochs）" extra="模型完整学习数据集的次数。轮数越多耗时越长，并不保证效果持续提升。"><InputNumber min={1} max={1000} /></Form.Item><Form.Item name="batch" label="每批图片数（Batch）" extra="同时参与一次计算的图片数。值越大占用内存越多；CPU 环境建议保持系统给出的上限。"><InputNumber min={1} max={activeDevice === 'cpu' ? activeCpuPolicy.maxBatch : 128} /></Form.Item><Form.Item name="imageSize" label="输入图像尺寸" extra="较大尺寸有利于小目标，但会显著增加内存和训练时间。常规任务建议从 640 开始。"><InputNumber min={320} max={activeDevice === 'cpu' ? activeCpuPolicy.maxImageSize : 2048} step={32} /></Form.Item></>}
          <Form.Item name="device" label="设备"><Select options={[{ value: 'cpu', label: 'CPU' }, { value: 'cuda:0', label: 'CUDA 0（GPU）' }]} /></Form.Item>
        </div>
        {activePreset === 'custom' && <Collapse ghost items={[{ key: 'augmentation', label: '高级数据增强', children: <>
          <Alert type="info" showIcon message="增强参数只影响训练，不会修改已发布的数据集。建议一次只调整一组参数，并对比验证集指标。" />
          <div className="form-grid">
            <Form.Item name={['augmentation', 'mosaic']} label="Mosaic"><InputNumber min={0} max={1} step={0.1} /></Form.Item>
            <Form.Item name={['augmentation', 'mixup']} label="MixUp"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
            <Form.Item name={['augmentation', 'copy_paste']} label="Copy-Paste"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
            <Form.Item name={['augmentation', 'degrees']} label="旋转角度"><InputNumber min={0} max={45} step={1} /></Form.Item>
            <Form.Item name={['augmentation', 'translate']} label="平移比例"><InputNumber min={0} max={0.5} step={0.05} /></Form.Item>
            <Form.Item name={['augmentation', 'scale']} label="缩放幅度"><InputNumber min={0} max={0.9} step={0.05} /></Form.Item>
            <Form.Item name={['augmentation', 'fliplr']} label="水平翻转概率"><InputNumber min={0} max={1} step={0.1} /></Form.Item>
            <Form.Item name={['augmentation', 'hsv_h']} label="色相扰动"><InputNumber min={0} max={0.1} step={0.005} /></Form.Item>
            <Form.Item name={['augmentation', 'hsv_s']} label="饱和度扰动"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
            <Form.Item name={['augmentation', 'hsv_v']} label="明度扰动"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
          </div>
        </> }]} />}
      </Form>
    </Drawer>
    <Drawer className="mobile-fullscreen-drawer" width={isMobile ? '100%' : 'min(1080px, 94vw)'} title={selected?.name} open={Boolean(selected)} onClose={() => setSelected(undefined)} extra={selected && <Space>{selected.status === 'completed' && <Button type="primary" icon={<Box size={15} />} onClick={() => { setRegisterRun(selected); modelForm.setFieldsValue({ name: selected.name, version: '1.0.0' }) }}>注册候选模型</Button>}{['queued','running'].includes(selected.status) ? <Button danger icon={<Square size={15} />} onClick={() => void cancelRun(selected)}>停止</Button> : <Dropdown trigger={['click']} menu={{ items:[{key:'record',label:'仅删除训练记录'},{key:'artifacts',label:'删除记录并清理训练产物',danger:true},{key:'cascade',label:'级联删除全部下游数据',danger:true}],onClick:({key})=>deleteRun(selected,key!=='record',key==='cascade') }}><Button icon={<MoreHorizontal size={15}/>}>删除与清理</Button></Dropdown>}</Space>}>
      {selected && <div className="training-detail-drawer"><div className="detail-status"><TaskTag task={selected.task} /><StatusTag status={selected.status} /><span>{selected.duration}</span><strong>Epoch {selected.epoch}/{selected.epochs}</strong></div>
        {detailsLoading && !details ? <div className="training-detail-loading"><Spin /></div> : details ? <Tabs defaultActiveKey="overview" items={[
          { key: 'overview', label: '实时概览', children: <TrainingOverviewTab run={selected} details={details} recoveryPending={recoveryPending} onSafeRetry={() => void recoverRun('safe')} onEvaluateBest={() => void recoverRun('evaluation')} /> },
          { key: 'charts', label: '指标曲线', children: <TrainingChartsTab details={details} /> },
          { key: 'results', label: `结果图像 (${details.artifacts.filter((item) => item.kind === 'image').length})`, children: <TrainingResultsTab details={details} /> },
          { key: 'artifacts', label: `参数与产物 (${details.artifacts.length})`, children: <TrainingArtifactsTab details={details} /> },
        ]} /> : null}
      </div>}
    </Drawer>
    <Modal title="注册候选模型" open={Boolean(registerRun)} onCancel={() => setRegisterRun(undefined)} onOk={() => void registerModel()} okText="注册">
      <Form form={modelForm} layout="vertical">
        <Form.Item name="name" label="模型名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="version" label="语义版本" rules={[{ required: true, pattern: /^\d+\.\d+\.\d+$/, message: '请输入例如 1.0.0 的语义版本' }]}><Input /></Form.Item>
      </Form>
    </Modal>
  </div>
}
