import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Drawer,
  Dropdown,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  Modal,
  Pagination,
  Progress,
  Row,
  Select,
  Skeleton,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Upload as AntUpload,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  Activity,
  ArrowRight,
  Box,
  Boxes,
  Check,
  CircleHelp,
  Database,
  Download,
  Eye,
  FlaskConical,
  FolderArchive,
  Gauge,
  HardDrive,
  Images,
  MoreHorizontal,
  Pencil,
  Play,
  PencilRuler,
  Plus,
  RefreshCw,
  ScanSearch,
  Server,
  Upload,
  Video,
  Trash2,
  X,
} from 'lucide-react'
import dayjs from 'dayjs'
import { navigationLabels, navigationMenuItems, pathForView, viewFromPath, type ViewKey } from './navigation'
import { navigationDecision } from './navigationGuard'
import { historyTravel } from './navigationHistory'
import { applyBulkStatus, effectiveFrameStatus, selectFrameRange, type ReviewStatusFilter } from './pages/review/bulkSelection'
import { formatRecycleBytes, formatRecycleExpiry, recyclePurgeConfirmation, recycleTrashConfirmation } from './pages/review/frameRecyclePresentation'
import { formatReleaseSplit } from './pages/datasets/releaseSplit'
import { formatDatasetReleaseLabel } from './pages/datasets/datasetReleasePresentation'
import { buildDisplayNamePayload, taskDisplayNameRows, type TaskDisplayNameRow } from './pages/tasks/taskDisplayNames'
import { IMAGE_UPLOAD_GUIDANCE, uploadLimitError } from './uploadPolicy'
import { parseReviewUrlState, reviewUrlSearch } from './pages/review/reviewUrlState'
import { reviewStatusLabel } from './pages/review/reviewStatusPresentation'
import { createRequestId } from './requestId'
import { MobileBottomNavigation } from './components/mobile/MobileBottomNavigation'
import { MobileRecordCard } from './components/mobile/MobileRecordCard'
import { useMobileViewport } from './responsive/useMobileViewport'
import {
  api,
  type DashboardSummary,
  type DatasetReleaseSummary,
  type FrameAssetSummary,
  type HealthStatus,
  type JobStatus,
  type TaskSummary,
  type VideoCollectionSummary,
  type DuplicateGroupSummary,
  type RecycledFrameSummary,
  type RecycleBinSummary,
} from './api'

const { Header, Sider, Content } = Layout

const PlatformDashboardPage = lazy(() => import('./pages/platform/DashboardPage'))
const TrainingPage = lazy(() => import('./pages/platform/TrainingPage'))
const ModelsPage = lazy(() => import('./pages/platform/ModelsPage'))
const InferencePage = lazy(() => import('./pages/platform/InferencePage'))
const AnnotationPage = lazy(() => import('./pages/annotation/AnnotationPage'))
const HelpCenterPage = lazy(() => import('./pages/help/HelpCenterPage'))

const formatBytes = (value: number) => {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

type NavigationGuardRegistration = {
  pendingCount: number
  save: () => Promise<void>
  discard: () => void
}

function App() {
  const isMobile = useMobileViewport()
  const [view, setView] = useState<ViewKey>(() => viewFromPath(window.location.pathname))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [collections, setCollections] = useState<VideoCollectionSummary[]>([])
  const [releases, setReleases] = useState<DatasetReleaseSummary[]>([])
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const navigationGuard = useRef<NavigationGuardRegistration | null>(null)
  const viewRef = useRef(view)
  const historyPositionRef = useRef<number>(Number.isInteger(window.history.state?.position) ? window.history.state.position : 0)
  const pendingHistoryTravel = useRef<{ targetView: ViewKey; targetPosition: number; resumeDelta: number } | null>(null)
  const allowHistoryTravel = useRef(false)
  const lastReviewSearch = useRef(view === 'review' ? window.location.search : '')

  // Global Job Progress state
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [nextSummary, nextTasks, nextCollections, nextReleases, nextHealth] =
        await Promise.all([
          api.dashboard(),
          api.tasks(),
          api.collections(),
          api.releases(),
          api.health(),
        ])
      setSummary(nextSummary)
      setTasks(nextTasks)
      setCollections(nextCollections)
      setReleases(nextReleases)
      setHealth(nextHealth)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法连接后端服务')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const commitNavigation = useCallback((nextView: ViewKey, replace = false) => {
    if (viewRef.current === 'review') lastReviewSearch.current = window.location.search
    const path = `${pathForView(nextView)}${nextView === 'review' ? lastReviewSearch.current : ''}`
    if (replace) window.history.replaceState({ view: nextView, position: historyPositionRef.current }, '', path)
    else {
      historyPositionRef.current += 1
      window.history.pushState({ view: nextView, position: historyPositionRef.current }, '', path)
    }
    viewRef.current = nextView
    setView(nextView)
  }, [])

  const navigate = useCallback((nextView: ViewKey, replace = false) => {
    const guard = navigationGuard.current
    const decision = navigationDecision(guard?.pendingCount ?? 0, viewRef.current, nextView)
    if (decision === 'stay') return
    if (decision === 'navigate' || !guard) {
      commitNavigation(nextView, replace)
      return
    }

    let dialog: ReturnType<typeof Modal.confirm>
    dialog = Modal.confirm({
      title: '存在未保存的筛选修改',
      content: <div><p>当前有 {guard.pendingCount} 项图片状态尚未同步到数据库。</p><Button danger type="link" onClick={() => { guard.discard(); dialog.destroy(); commitNavigation(nextView, replace) }}>放弃修改并离开</Button></div>,
      okText: '保存并离开',
      cancelText: '继续编辑',
      onOk: async () => { await guard.save(); commitNavigation(nextView, replace) },
    })
  }, [commitNavigation])

  useEffect(() => {
    const initialView = viewFromPath(window.location.pathname)
    window.history.replaceState(
      { ...window.history.state, view: initialView, position: historyPositionRef.current },
      '',
      window.location.pathname === '/' ? pathForView('dashboard') : `${window.location.pathname}${window.location.search}`,
    )
    const onPopState = () => {
      const target = viewFromPath(window.location.pathname)
      const targetPosition = Number.isInteger(window.history.state?.position) ? window.history.state.position as number : undefined
      if (allowHistoryTravel.current) {
        allowHistoryTravel.current = false
        if (targetPosition != null) historyPositionRef.current = targetPosition
        viewRef.current = target
        setView(target)
        return
      }
      const pending = pendingHistoryTravel.current
      if (pending && targetPosition === historyPositionRef.current) {
        pendingHistoryTravel.current = null
        const guard = navigationGuard.current
        if (!guard) return
        let dialog: ReturnType<typeof Modal.confirm>
        const resume = () => { allowHistoryTravel.current = true; window.history.go(pending.resumeDelta) }
        dialog = Modal.confirm({
          title: '存在未保存的筛选修改',
          content: <div><p>当前有 {guard.pendingCount} 项图片状态尚未同步到数据库。</p><Button danger type="link" onClick={() => { guard.discard(); dialog.destroy(); resume() }}>放弃修改并离开</Button></div>,
          okText: '保存并离开',
          cancelText: '继续编辑',
          onOk: async () => { await guard.save(); resume() },
        })
        return
      }
      const travel = historyTravel(historyPositionRef.current, targetPosition)
      if ((navigationGuard.current?.pendingCount ?? 0) > 0 && target !== viewRef.current && travel && targetPosition != null) {
        pendingHistoryTravel.current = { targetView: target, targetPosition, resumeDelta: travel.resumeDelta }
        window.history.go(travel.restoreDelta)
        return
      }
      if (targetPosition != null) historyPositionRef.current = targetPosition
      viewRef.current = target
      setView(target)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [navigate])

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if ((navigationGuard.current?.pendingCount ?? 0) === 0) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  // Poll background job if active
  useEffect(() => {
    if (!activeJobId) return
    let timer: number
    const poll = async () => {
      try {
        const status = await api.getJobStatus(activeJobId)
        setJobStatus(status)
        if (status.status === 'completed' || status.status === 'failed') {
          setActiveJobId(null)
          if (status.status === 'completed') {
            message.success('后台任务执行成功！')
          } else {
            message.error(`任务失败：${status.message}`)
          }
          void load()
        } else {
          timer = window.setTimeout(poll, 1500)
        }
      } catch (e) {
        setActiveJobId(null)
        setJobStatus(null)
        message.error('无法轮询后台任务 status')
      }
    }
    void poll()
    return () => clearTimeout(timer)
  }, [activeJobId])

  const title = navigationLabels[view]

  return (
    <Layout className="app-shell">
      <Sider width={232} className="sidebar">
        <div className="brand">
          <div className="brand-mark">TF</div>
          <div className="brand-copy">
            <strong>TrainForge</strong>
            <span>模型工程平台</span>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[view]}
          items={navigationMenuItems}
          onClick={({ key }) => navigate(key as ViewKey)}
        />
        <div className="sidebar-status">
          <Activity size={16} />
          <span>{health?.status === 'ok' ? '服务正常' : '等待连接'}</span>
        </div>
      </Sider>
      <Layout>
        <Header className="topbar">
          <div>
            <h1>{title}</h1>
            <span>{dayjs().format('YYYY年MM月DD日')}</span>
          </div>
          <Space>
            {jobStatus && activeJobId && (
              <div className="pipeline-running-mini" style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <Spin size="small" />
                <span>{jobStatus.message} ({jobStatus.progress}%)</span>
                <Progress percent={Math.round(jobStatus.progress)} size="small" style={{ width: 80, margin: 0 }} />
              </div>
            )}
            <Tooltip title="刷新全部数据">
              <Button icon={<RefreshCw size={17} />} onClick={() => void load()} loading={loading} />
            </Tooltip>
          </Space>
        </Header>
        <Content className="content">
          {error && <Alert type="error" showIcon message="服务连接失败" description={error} style={{ marginBottom: 16 }} />}
          {jobStatus && (jobStatus.status === 'running' || jobStatus.status === 'pending') && (
            <div className="job-progress-wrapper">
              <div className="job-progress-header">
                <span>后台正在执行操作：{jobStatus.message}</span>
                <Tag color="processing">{jobStatus.status.toUpperCase()}</Tag>
              </div>
              <Progress percent={Math.round(jobStatus.progress)} status="active" />
            </div>
          )}
          {loading && !summary ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : (
            <View
              view={view}
              summary={summary}
              tasks={tasks}
              collections={collections}
              releases={releases}
              health={health}
              onNavigate={navigate}
              onNavigationGuardChange={(guard) => { navigationGuard.current = guard }}
              onJobStarted={(jobId) => setActiveJobId(jobId)}
              refreshDashboard={() => void load()}
            />
          )}
        </Content>
      </Layout>
      {isMobile && <MobileBottomNavigation activeView={view} onNavigate={navigate} />}
    </Layout>
  )
}

function View(props: {
  view: ViewKey
  summary: DashboardSummary | null
  tasks: TaskSummary[]
  collections: VideoCollectionSummary[]
  releases: DatasetReleaseSummary[]
  health: HealthStatus | null
  onNavigate: (view: ViewKey) => void
  onNavigationGuardChange: (guard: NavigationGuardRegistration | null) => void
  onJobStarted: (jobId: string) => void
  refreshDashboard: () => void
}) {
  if (props.view === 'dashboard') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><PlatformDashboardPage onNavigate={props.onNavigate} /></Suspense>
  if (props.view === 'training') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><TrainingPage /></Suspense>
  if (props.view === 'models') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><ModelsPage /></Suspense>
  if (props.view === 'inference') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><InferencePage /></Suspense>
  if (props.view === 'annotation') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><AnnotationPage tasks={props.tasks} onNavigate={props.onNavigate} refreshDashboard={props.refreshDashboard} /></Suspense>
  if (props.view === 'help') return <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}><HelpCenterPage /></Suspense>
  if (props.view === 'tasks') return <TasksTable data={props.tasks} refreshDashboard={props.refreshDashboard} />
  if (props.view === 'videos') {
    return (
      <VideosView
        collections={props.collections}
        tasks={props.tasks}
        onJobStarted={props.onJobStarted}
        refreshDashboard={props.refreshDashboard}
      />
    )
  }
  if (props.view === 'review') {
    return (
      <ReviewWorkspace
        collections={props.collections}
        tasks={props.tasks}
        releases={props.releases}
        refreshDashboard={props.refreshDashboard}
        onNavigate={props.onNavigate}
        onNavigationGuardChange={props.onNavigationGuardChange}
        onJobStarted={props.onJobStarted}
      />
    )
  }
  if (props.view === 'datasets') return <DatasetWorkspace data={props.releases} tasks={props.tasks} refreshDashboard={props.refreshDashboard} />
  if (props.view === 'system') return <SystemView health={props.health} />
  return <Dashboard data={props.summary} releases={props.releases} />
}

function Dashboard({ data, releases }: { data: DashboardSummary | null; releases: DatasetReleaseSummary[] }) {
  const stats = useMemo(
    () => [
      { label: '业务任务', value: data?.tasks ?? 0, icon: Boxes, tone: 'green' },
      { label: '归档视频', value: data?.video_assets ?? 0, icon: Video, tone: 'blue' },
      { label: '抽帧批次', value: data?.frame_batches ?? 0, icon: FolderArchive, tone: 'amber' },
      { label: '标注导入', value: data?.annotation_exports ?? 0, icon: HardDrive, tone: 'red' },
      { label: '数据集版本', value: data?.dataset_releases ?? 0, icon: Database, tone: 'teal' },
    ],
    [data],
  )
  return (
    <div className="stack">
      <section className="stats-grid">
        {stats.map(({ label, value, icon: Icon, tone }) => (
          <div className="metric" key={label}>
            <span className={`metric-icon ${tone}`}><Icon size={21} /></span>
            <div><span>{label}</span><strong>{value}</strong></div>
          </div>
        ))}
      </section>
      <section className="workspace-grid">
        <div className="panel pipeline-panel">
          <div className="panel-heading"><div><h2>数据流水线</h2><p>当前资源分布</p></div><Tag color="green">Phase 1</Tag></div>
          <div className="pipeline">
            {[
              ['视频归档', data?.video_collections ?? 0],
              ['抽帧筛选', data?.frame_batches ?? 0],
              ['标注回导', data?.annotation_exports ?? 0],
              ['版本发布', data?.dataset_releases ?? 0],
            ].map(([label, value], index) => (
              <div className="pipeline-step" key={String(label)}>
                <span>{index + 1}</span><div><strong>{label}</strong><small>{value} 个批次</small></div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-heading"><div><h2>最近发布</h2><p>不可变数据集版本</p></div></div>
          {releases.length ? <ReleasesTable data={releases.slice(0, 4)} compact /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已发布数据集" />}
        </div>
      </section>
    </div>
  )
}

function TasksTable({ data, refreshDashboard }: { data: TaskSummary[]; refreshDashboard: () => void }) {
  const [open, setOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<TaskSummary>()
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm<{ rows: TaskDisplayNameRow[] }>()
  const resetTaskForm = () => {
    form.resetFields()
    form.setFieldsValue({ task_type: 'detect', class_rows: [{ name: '', display_name: '' }] })
  }
  const openTaskForm = () => {
    resetTaskForm()
    setOpen(true)
  }
  const closeTaskForm = () => {
    setOpen(false)
    resetTaskForm()
  }
  const deleteTask = (task: TaskSummary, cascade: boolean) => Modal.confirm({
    title: cascade ? `级联删除任务 ${task.id}？` : `删除任务 ${task.id}？`,
    content: cascade ? '将永久删除该任务的图片、视频、标注、数据集、训练、模型、推理记录和全部托管产物。此操作不可恢复。' : '仅当任务没有任何下游数据时才会删除；存在依赖时系统会拒绝操作。',
    okText: cascade ? '确认级联删除' : '确认删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: async () => {
      try {
        await api.deleteTask(task.id, true, cascade)
        await refreshDashboard()
        message.success(cascade ? '任务及全部下游数据已删除' : '任务已删除')
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除任务失败')
        throw error
      }
    },
  })
  const createTask = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const rows = values.class_rows as Array<{ name: string; display_name?: string }>
      await api.createTask({
        id: values.id,
        task_type: values.task_type,
        classes: rows.map((row) => row.name.trim()),
        class_display_names: Object.fromEntries(rows.filter((row) => row.display_name?.trim()).map((row) => [row.name.trim(), row.display_name!.trim()])),
      })
      closeTaskForm()
      refreshDashboard()
      message.success('任务创建成功，可以继续导入图片或视频')
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSubmitting(false)
    }
  }
  const updateTask = async () => {
    if (!editingTask) return
    try {
      const values = await editForm.validateFields()
      setSubmitting(true)
      await api.updateTask(editingTask.id, buildDisplayNamePayload(values.rows))
      setEditingTask(undefined)
      await refreshDashboard()
      message.success('中文类别名称已更新，标注页面将立即使用新名称')
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSubmitting(false)
    }
  }
  return <>
    <section className="panel table-panel">
      <div className="panel-heading"><div><h2>任务管理</h2><p>定义任务类型和稳定的类别契约，后续数据、训练和模型均归属于任务</p></div><Button type="primary" icon={<Plus size={16} />} onClick={openTaskForm}>新建任务</Button></div>
      {data.length ? <div className="task-contract-list">
        {data.map((task) => <article className="task-contract-card" key={task.id}>
          <div className="task-contract-identity">
            <span>任务契约</span>
            <strong>{task.id}</strong>
            <Tag color={task.task_type === 'detect' ? 'blue' : 'purple'}>{task.task_type}</Tag>
          </div>
          <div className="task-contract-classes">
            <div className="task-contract-section-label">类别 <span>{task.classes.length}</span></div>
            <div className="tag-list">
              {task.classes.map((value) => <Tag key={value}>{task.class_display_names[value] ? `${task.class_display_names[value]}（${value}）` : value}</Tag>)}
            </div>
          </div>
          <dl className="task-contract-meta">
            <div><dt>标注格式</dt><dd>{task.annotation_format}</dd></div>
            <div><dt>创建时间</dt><dd><time>{dayjs(task.created_at).format('YYYY-MM-DD HH:mm')}</time></dd></div>
          </dl>
          <div className="task-contract-actions">
            <Tooltip title="编辑中文显示名称"><Button aria-label={`编辑 ${task.id} 的中文显示名称`} icon={<Pencil size={14} />} onClick={() => {
              setEditingTask(task)
              editForm.setFieldsValue({ rows: taskDisplayNameRows(task.classes, task.class_display_names) })
            }} /></Tooltip>
            <Dropdown trigger={['click']} menu={{ items: [
              { key: 'delete', label: '安全删除任务', danger: true },
              { key: 'cascade', label: '级联删除全部数据', danger: true },
            ], onClick: ({ key }) => deleteTask(task, key === 'cascade') }}>
              <Tooltip title="更多删除操作"><Button aria-label={`更多 ${task.id} 删除操作`} icon={<MoreHorizontal size={15} />} /></Tooltip>
            </Dropdown>
          </div>
        </article>)}
      </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务，请先创建检测或分割任务" />}
    </section>
    <Modal title="新建 YOLO 任务" open={open} okText="创建任务" cancelText="取消" confirmLoading={submitting} onOk={() => void createTask()} onCancel={closeTaskForm} afterClose={resetTaskForm} destroyOnHidden>
      <Alert type="info" showIcon message="类别顺序会决定 YOLO 标签中的 class id，任务投入使用后请保持稳定。" style={{ marginBottom: 18 }} />
      <Form form={form} layout="vertical" initialValues={{ task_type: 'detect', class_rows: [{ name: '', display_name: '' }] }}>
        <Form.Item name="id" label="任务系统标识" extra="用于数据目录、接口和训练记录。创建后不建议修改；请使用小写字母、数字和连字符，例如 surface-defects。" rules={[{ required: true, message: '请输入任务系统标识' }, { pattern: /^[a-z0-9]+(?:-[a-z0-9]+)*$/, message: '请使用小写字母、数字和连字符，例如 surface-defects' }]}><Input placeholder="surface-defects" /></Form.Item>
        <Form.Item name="task_type" label="任务类型" rules={[{ required: true }]}><Select options={[{ value: 'detect', label: '目标检测（矩形框 / yolo-detect）' }, { value: 'segment', label: '实例分割（多边形 / yolo-seg）' }]} /></Form.Item>
        <Form.Item label="标注类别" extra="class id 按行顺序从 0 开始；英文标识用于训练，中文名称用于界面识别。" required>
          <Form.List name="class_rows">
            {(fields, { add, remove }) => <Space direction="vertical" style={{ width: '100%' }}>
              {fields.map((field, index) => <Space.Compact block key={field.key}>
                <Form.Item noStyle name={[field.name, 'name']} rules={[{ required: true, message: '请输入英文标识' }, { pattern: /^[A-Za-z0-9_-]+$/, message: '仅支持字母、数字、_ 和 -' }]}><Input addonBefore={`ID ${index}`} placeholder="scratch" /></Form.Item>
                <Form.Item noStyle name={[field.name, 'display_name']}><Input placeholder="中文显示名，例如：划痕" /></Form.Item>
                <Button danger icon={<Trash2 size={15} />} disabled={fields.length === 1} onClick={() => remove(field.name)} />
              </Space.Compact>)}
              <Button type="dashed" icon={<Plus size={15} />} onClick={() => add({ name: '', display_name: '' })}>添加类别</Button>
            </Space>}
          </Form.List>
        </Form.Item>
      </Form>
    </Modal>
    <Modal title={`编辑类别中文名称 · ${editingTask?.id ?? ''}`} open={Boolean(editingTask)} okText="保存中文名称" cancelText="取消" confirmLoading={submitting} onOk={() => void updateTask()} onCancel={() => setEditingTask(undefined)} destroyOnHidden>
      <Alert type="info" showIcon message="Class ID、英文标识和顺序已锁定，只修改界面显示的中文名称，不会影响已有 YOLO 标注。" style={{ marginBottom: 18 }} />
      <Form form={editForm} layout="vertical">
        <Form.List name="rows">{(fields) => <Space direction="vertical" style={{ width: '100%' }}>
          {fields.map((field, index) => {
            const className = editingTask?.classes[index] ?? ''
            return <div className="task-class-edit-row" key={field.key}>
              <div><strong>ID {index}</strong><code>{className}</code></div>
              <Form.Item name={[field.name, 'classId']} hidden><InputNumber /></Form.Item>
              <Form.Item name={[field.name, 'className']} hidden><Input /></Form.Item>
              <Form.Item name={[field.name, 'displayName']} label="中文显示名称" style={{ margin: 0 }}><Input allowClear placeholder="例如：电梯编号标签" /></Form.Item>
            </div>
          })}
        </Space>}</Form.List>
      </Form>
    </Modal>
  </>
}

// Interactive Videos View (Import & Extract)
function VideosView(props: {
  collections: VideoCollectionSummary[]
  tasks: TaskSummary[]
  onJobStarted: (jobId: string) => void
  refreshDashboard: () => void
}) {
  const [importVisible, setImportVisible] = useState(false)
  const [extractVisible, setExtractVisible] = useState(false)
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)
  const [importFiles, setImportFiles] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadingVideos, setUploadingVideos] = useState(false)

  const [importForm] = Form.useForm()
  const [extractForm] = Form.useForm()

  const onImportSubmit = async (values: any) => {
    if (!importFiles.length) return message.warning('请选择至少一个视频文件')
    try {
      setUploadingVideos(true)
      setUploadProgress(0)
      const res = await api.uploadVideos(values.task_id, values.collection_id, importFiles, setUploadProgress)
      props.onJobStarted(res.job_id)
      setImportVisible(false)
      setImportFiles([])
      importForm.resetFields()
      message.success(`已上传 ${res.uploaded_count} 个视频，正在后台归档`)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导入失败')
    } finally {
      setUploadingVideos(false)
      setUploadProgress(0)
    }
  }

  const onExtractSubmit = async (values: any) => {
    try {
      const res = await api.extractFrames(
        values.collection_id,
        values.batch_id,
        values.interval,
        values.quality
      )
      props.onJobStarted(res.job_id)
      setExtractVisible(false)
      extractForm.resetFields()
      message.success('已提交后台视频抽帧任务')
    } catch (e) {
      message.error(e instanceof Error ? e.message : '抽帧失败')
    }
  }

  const deleteCollection = (record: VideoCollectionSummary, deleteArtifacts: boolean, cascade = false) => Modal.confirm({ title: cascade ? '级联删除视频集合？' : deleteArtifacts ? '删除视频集合和归档文件？' : '删除视频集合记录？', content: cascade ? '将永久删除集合、所有抽帧批次、帧标注和归档文件。' : '集合存在抽帧批次时会拒绝删除，请先在数据筛选页删除对应批次，或使用级联删除。', okText: cascade ? '确认级联删除' : deleteArtifacts ? '永久删除' : '删除记录', okButtonProps: { danger: true }, onOk: async () => { try { await api.deleteVideoCollection(record.id, deleteArtifacts, cascade); await props.refreshDashboard(); message.success(cascade ? '视频集合及抽帧数据已删除' : '视频集合已删除') } catch (error) { message.error(error instanceof Error ? error.message : '删除视频集合失败'); throw error } } })

  const openExtractForm = (record: VideoCollectionSummary) => {
    setSelectedCollectionId(record.id)
    extractForm.setFieldsValue({
      collection_id: record.id,
      batch_id: `batch-${record.id}-${dayjs().format('MMDD')}`,
      interval: 1.0,
      quality: 95,
    })
    setExtractVisible(true)
  }
  const importSummary = {
    batches: props.collections.length,
    videos: props.collections.reduce((total, collection) => total + collection.asset_count, 0),
    bytes: props.collections.reduce((total, collection) => total + collection.total_size_bytes, 0),
  }

  return (
    <div className="stack">
      <section className="panel table-panel">
        <div className="panel-heading import-panel-heading">
          <div>
            <h2>视频归档</h2>
            <p>源文件保留，归档副本按哈希管理</p>
          </div>
          <div className="import-panel-heading-actions">
            <div className="import-summary" aria-label="归档汇总">
              <span><strong>{importSummary.batches}</strong> 批次</span>
              <span><strong>{importSummary.videos}</strong> 视频</span>
              <span><strong>{formatBytes(importSummary.bytes)}</strong> 已归档</span>
            </div>
            <Button type="primary" icon={<Plus size={16} />} onClick={() => setImportVisible(true)}>上传新批次</Button>
          </div>
        </div>
        {props.collections.length ? <div className="import-batch-list">
          {props.collections.map((record) => <article className="import-batch-card" key={record.id}>
            <div className="import-batch-identity">
              <span>采集批次</span>
              <strong title={record.id}>{record.id}</strong>
              <code title={record.task_id}>{record.task_id}</code>
            </div>
            <dl className="import-batch-storage">
              <div><dt>视频数量</dt><dd>{record.asset_count}<small> 个文件</small></dd></div>
              <div><dt>归档容量</dt><dd>{formatBytes(record.total_size_bytes)}</dd></div>
            </dl>
            <div className="import-batch-timeline"><span>导入时间</span><time>{dayjs(record.created_at).format('YYYY-MM-DD HH:mm')}</time></div>
            <div className="import-batch-actions">
              <Button type="primary" icon={<Play size={13} />} onClick={() => openExtractForm(record)}>启动抽帧</Button>
              <Dropdown trigger={['click']} menu={{ items: [
                { key: 'record', label: '仅删除集合记录' },
                { key: 'artifacts', label: '删除记录并清理归档视频', danger: true },
                { key: 'cascade', label: '级联删除全部下游数据', danger: true },
              ], onClick: ({ key }) => deleteCollection(record, key !== 'record', key === 'cascade') }}>
                <Tooltip title="删除与清理"><Button aria-label={`管理 ${record.id}`} icon={<MoreHorizontal size={16} />} /></Tooltip>
              </Dropdown>
            </div>
          </article>)}
        </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无视频归档，请先上传一个采集批次" />}
      </section>

      {/* Video Import Modal */}
      <Modal
        title="上传新视频采集批次"
        open={importVisible}
        confirmLoading={uploadingVideos}
        okText={uploadingVideos ? '上传中' : '上传并归档'}
        okButtonProps={{ disabled: importFiles.length === 0 }}
        closable={!uploadingVideos}
        maskClosable={!uploadingVideos}
        onCancel={() => { if (!uploadingVideos) { setImportVisible(false); setImportFiles([]); setUploadProgress(0); importForm.resetFields() } }}
        onOk={() => importForm.submit()}
        destroyOnHidden
      >
        <Form form={importForm} layout="vertical" onFinish={onImportSubmit}>
          <Form.Item
            name="task_id"
            label="绑定业务任务"
            rules={[{ required: true, message: '请选择绑定任务' }]}
          >
            <Select placeholder="选择关联的业务任务">
              {props.tasks.map((t) => (
                <Select.Option key={t.id} value={t.id}>
                  {t.id} ({t.task_type === 'detect' ? '检测' : '分割'})
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="collection_id"
            label="采集批次 ID (Collection ID)"
            rules={[{ required: true, message: '请输入采集批次 ID' }]}
          >
            <Input placeholder="例如: signal-light-collection-001" />
          </Form.Item>
          <Form.Item
            label="视频文件"
            required
            extra="支持 MP4、AVI、MOV、MKV、M4V，最多 50 个文件；单次请求总计不超过 20 GB，实际可上传容量还受服务器剩余磁盘影响。"
          >
            <AntUpload.Dragger
              multiple
              maxCount={50}
              accept=".mp4,.avi,.mov,.mkv,.m4v,video/*"
              beforeUpload={() => false}
              disabled={uploadingVideos}
              fileList={importFiles.map((file, index) => ({ uid: `${index}-${file.name}-${file.size}`, name: file.name, size: file.size, status: 'done', originFileObj: file } as any))}
              onChange={({ fileList }) => { const files = fileList.map((item) => item.originFileObj).filter(Boolean) as File[]; const error = uploadLimitError(files, 'video'); if (error) message.error(error); else setImportFiles(files) }}
              onRemove={(file) => { setImportFiles((items) => items.filter((item) => item.name !== file.name)); return true }}
            >
              <p className="ant-upload-drag-icon"><Video size={38} /></p>
              <p>拖入视频或点击选择文件</p>
              <p className="ant-upload-hint">可一次选择多个视频，上传完成后自动创建采集批次</p>
            </AntUpload.Dragger>
          </Form.Item>
          {uploadingVideos && <Progress percent={uploadProgress} status="active" />}
        </Form>
      </Modal>

      {/* Frame Extract Modal */}
      <Modal
        title="启动定时抽帧"
        open={extractVisible}
        onCancel={() => setExtractVisible(false)}
        onOk={() => extractForm.submit()}
      >
        <Form form={extractForm} layout="vertical" onFinish={onExtractSubmit}>
          <Form.Item name="collection_id" label="所选采集批次">
            <Input disabled />
          </Form.Item>
          <Form.Item
            name="batch_id"
            label="生成抽帧批次 ID (Batch ID)"
            rules={[{ required: true, message: '请输入抽帧批次 ID' }]}
          >
            <Input placeholder="例如: frames-signal-light-001" />
          </Form.Item>
          <Form.Item
            name="interval"
            label="抽帧时间间隔 (秒)"
            rules={[{ required: true, message: '请输入抽帧间隔' }]}
          >
            <InputNumber min={0.1} max={60.0} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="quality"
            label={<Space size={4}>JPEG 图像保存画质<Tooltip title="推荐设置为 90–95。数值越低越节省空间，但压缩模糊和伪影可能影响小目标、文字和边缘标注质量。"><CircleHelp size={14} /></Tooltip></Space>}
            rules={[{ required: true, message: '请输入画质' }]}
          >
            <InputNumber min={50} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// Review Workspace (Interactive Grid & Actions)
function ReviewWorkspace(props: {
  collections: VideoCollectionSummary[]
  tasks: TaskSummary[]
  releases: DatasetReleaseSummary[]
  refreshDashboard: () => void
  onNavigate: (view: ViewKey) => void
  onNavigationGuardChange: (guard: NavigationGuardRegistration | null) => void
  onJobStarted: (jobId: string) => void
}) {
  const initialUrlState = useRef(parseReviewUrlState(window.location.search)).current
  const restoreInitialContext = useRef(Boolean(initialUrlState.batch))
  const [batches, setBatches] = useState<{ id: string; collection_id: string }[]>([])
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(initialUrlState.batch)
  const [frames, setFrames] = useState<FrameAssetSummary[]>([])
  const [duplicates, setDuplicates] = useState<DuplicateGroupSummary[]>([])
  const [loading, setLoading] = useState(false)

  // Selections change buffer: filename -> targetStatus
  const [pendingSelections, setPendingSelections] = useState<Record<string, string>>({})
  const [selectedFrameNames, setSelectedFrameNames] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState<ReviewStatusFilter>(initialUrlState.status)
  const [selectionAnchor, setSelectionAnchor] = useState<string | null>(null)
  const [page, setPage] = useState(initialUrlState.page)
  const [pageSize, setPageSize] = useState(60)
  const [pageTotal, setPageTotal] = useState(0)
  const [statusCounts, setStatusCounts] = useState({ candidate: 0, selected: 0, rejected: 0, duplicate: 0 })
  const [searchInput, setSearchInput] = useState(initialUrlState.search)
  const [search, setSearch] = useState(initialUrlState.search)
  const [allMatching, setAllMatching] = useState(false)
  const [excludedFrameIds, setExcludedFrameIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [appendVisible, setAppendVisible] = useState(false)
  const [appendFiles, setAppendFiles] = useState<File[]>([])
  const [appendUploading, setAppendUploading] = useState(false)
  const [appendVideoVisible, setAppendVideoVisible] = useState(false)
  const [appendVideoFiles, setAppendVideoFiles] = useState<File[]>([])
  const [appendVideoUploading, setAppendVideoUploading] = useState(false)
  const [appendVideoProgress, setAppendVideoProgress] = useState(0)
  const [appendVideoInterval, setAppendVideoInterval] = useState(1)
  const [appendVideoQuality, setAppendVideoQuality] = useState(95)
  const [recycleOpen, setRecycleOpen] = useState(false)
  const [recycleLoading, setRecycleLoading] = useState(false)
  const [recycleItems, setRecycleItems] = useState<RecycledFrameSummary[]>([])
  const [recyclePage, setRecyclePage] = useState(1)
  const [recycleTotal, setRecycleTotal] = useState(0)
  const [recycleSummary, setRecycleSummary] = useState<RecycleBinSummary>({ item_count: 0, total_bytes: 0, earliest_purge_after: null })

  // Package & Import Release variables
  const [packageResult, setPackageResult] = useState<{ sha256: string; path: string; download_url: string } | null>(null)
  const [packaging, setPackaging] = useState(false)
  const [importVisible, setImportVisible] = useState(false)
  const [releaseVisible, setReleaseVisible] = useState(false)
  const [importedId, setImportedId] = useState<string | null>(null)
  const [annotationZip, setAnnotationZip] = useState<File | null>(null)
  const [annotationUploadProgress, setAnnotationUploadProgress] = useState(0)
  const [uploadingAnnotations, setUploadingAnnotations] = useState(false)

  const [importForm] = Form.useForm()
  const [releaseForm] = Form.useForm()

  const loadBatchesList = async () => {
    try {
      const res = await api.listBatches()
      setBatches(res)
      if (res.length > 0 && (!selectedBatchId || !res.some((batch) => batch.id === selectedBatchId))) {
        setSelectedBatchId(res[0].id)
      }
    } catch (e) {
      message.error('加载抽帧批次失败')
    }
  }

  const loadFramePage = async (batchId: string, nextPage: number, nextPageSize: number, nextFilter: ReviewStatusFilter, nextSearch: string) => {
    setLoading(true)
    try {
      const result = await api.listBatchFrames(batchId, nextPage, nextPageSize, nextFilter === 'all' ? undefined : nextFilter, nextSearch)
      setFrames(result.items); setPage(result.page); setPageSize(result.page_size); setPageTotal(result.total); setStatusCounts(result.status_counts)
    } catch (e) {
      message.error('加载批次详情失败')
    } finally {
      setLoading(false)
    }
  }

  const loadBatchDetails = async (batchId: string, resetContext = false) => {
    setPendingSelections({}); setSelectedFrameNames([]); setSelectionAnchor(null); setAllMatching(false); setExcludedFrameIds([])
    if (resetContext) { setStatusFilter('all'); setSearch(''); setSearchInput('') }
    const nextPage = resetContext ? 1 : page
    const nextFilter = resetContext ? 'all' : statusFilter
    const nextSearch = resetContext ? '' : search
    const [, dupRes] = await Promise.all([loadFramePage(batchId, nextPage, pageSize, nextFilter, nextSearch), api.getBatchDuplicates(batchId)])
    setDuplicates(dupRes)
  }

  useEffect(() => {
    void loadBatchesList()
    void api.getRecycleBinSummary().then(setRecycleSummary).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (selectedBatchId) {
      const shouldRestore = restoreInitialContext.current
      restoreInitialContext.current = false
      void loadBatchDetails(selectedBatchId, !shouldRestore)
    }
  }, [selectedBatchId])

  useEffect(() => {
    const url = `${pathForView('review')}${reviewUrlSearch({ batch: selectedBatchId, status: statusFilter, page, search })}`
    window.history.replaceState({ ...window.history.state, view: 'review' }, '', url)
  }, [selectedBatchId, statusFilter, page, search])

  // Stats calculation
  const stats = useMemo(() => {
    const counts = { ...statusCounts }

    frames.forEach((f) => {
      const status = pendingSelections[f.filename]
      if (!status) return
      const before = f.status.startsWith('rejected') ? 'rejected' : f.status as 'candidate' | 'selected' | 'duplicate'
      const after = status.startsWith('rejected') ? 'rejected' : status as 'candidate' | 'selected' | 'duplicate'
      if (before !== after) { counts[before]--; counts[after]++ }
    })

    return { total: Object.values(counts).reduce((sum, value) => sum + value, 0), ...counts }
  }, [frames, pendingSelections, statusCounts])

  const visibleFrameNames = useMemo(() => frames.map((frame) => frame.filename), [frames])
  const visibleFrames = frames

  // Selection actions
  const changeStatus = (filename: string, status: string) => {
    setPendingSelections((prev) => ({
      ...prev,
      [filename]: status,
    }))
  }

  const toggleFrameSelection = (filename: string, shiftKey: boolean) => {
    const frame = frames.find((item) => item.filename === filename)
    if (allMatching && frame) {
      setExcludedFrameIds((current) => current.includes(frame.id) ? current.filter((id) => id !== frame.id) : [...current, frame.id])
      return
    }
    if (shiftKey && selectionAnchor) {
      setSelectedFrameNames((current) => selectFrameRange(visibleFrameNames, current, filename, selectionAnchor))
    } else {
      setSelectedFrameNames((current) => current.includes(filename) ? current.filter((name) => name !== filename) : [...current, filename])
    }
    setSelectionAnchor(filename)
  }

  const bulkStatusOptions = [
    { label: '设为保留', value: 'selected' },
    { label: '恢复待筛选', value: 'candidate' },
    { label: '拒绝 - 模糊', value: 'rejected/blur' },
    { label: '拒绝 - 无目标', value: 'rejected/no-target' },
    { label: '拒绝 - 隐私泄漏', value: 'rejected/privacy' },
    { label: '拒绝 - 重复帧', value: 'rejected/duplicate' },
    { label: '拒绝 - 其他', value: 'rejected/other' },
  ]

  const applySelectedStatus = (status: string) => {
    if (allMatching && selectedBatchId) {
      Modal.confirm({ title: `批量修改 ${Math.max(0, pageTotal - excludedFrameIds.length)} 张图片？`, content: '该操作将作为后台任务立即同步文件和数据库。', okText: '确认执行', onOk: async () => {
        const result = await api.bulkFrameSelection(selectedBatchId, { selection: { mode: 'all_matching', status: statusFilter === 'all' ? undefined : statusFilter, search, excluded_ids: excludedFrameIds }, target_status: status })
        props.onJobStarted(result.job_id)
        for (;;) { const job = await api.getJobStatus(result.job_id); if (job.status === 'completed') break; if (job.status === 'failed') throw new Error(job.message); await new Promise((resolve) => window.setTimeout(resolve, 800)) }
        setAllMatching(false); setExcludedFrameIds([]); await loadFramePage(selectedBatchId, 1, pageSize, statusFilter, search); message.success(`已更新 ${result.affected_count} 张图片`)
      } })
      return
    }
    setPendingSelections((current) => applyBulkStatus(current, selectedFrameNames, status))
    message.success(`已在本地修改 ${selectedFrameNames.length} 张图片，保存后同步 DB`)
  }

  const handleQuickMarkDuplicates = () => {
    const duplicateNames = [...new Set(duplicates.flatMap((group) => group.duplicates.map((path) => path.split('/').pop() ?? '').filter(Boolean)))]
    Modal.confirm({
      title: `标记 ${duplicateNames.length} 张重复图片？`,
      content: '这些修改会先保存在本地，点击“保存本地筛选并同步 DB”后才会写入数据库。',
      okText: '确认标记',
      cancelText: '取消',
      onOk: () => {
        setPendingSelections((current) => ({ ...current, ...Object.fromEntries(duplicateNames.map((name) => [name, 'rejected/duplicate'])) }))
        message.success(`已在本地标记 ${duplicateNames.length} 张重复图片`)
      },
    })
  }

  const saveSelections = async () => {
    if (!selectedBatchId) return
    setSubmitting(true)
    try {
      await api.updateFrameSelection(selectedBatchId, pendingSelections)
      message.success('同步筛选状态成功！')
      void loadBatchDetails(selectedBatchId)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存筛选失败')
      throw e
    } finally {
      setSubmitting(false)
    }
  }

  const requestBatchChange = (nextBatchId: string) => {
    const pendingCount = Object.keys(pendingSelections).length
    if (pendingCount === 0) {
      setSelectedBatchId(nextBatchId)
      return
    }
    let dialog: ReturnType<typeof Modal.confirm>
    dialog = Modal.confirm({
      title: '切换批次前保存修改？',
      content: <div><p>当前批次有 {pendingCount} 项图片状态尚未同步到数据库。</p><Button danger type="link" onClick={() => { setPendingSelections({}); dialog.destroy(); setSelectedBatchId(nextBatchId) }}>放弃修改并切换</Button></div>,
      okText: '保存并切换',
      cancelText: '继续编辑',
      onOk: async () => { await saveSelections(); setSelectedBatchId(nextBatchId) },
    })
  }

  useEffect(() => {
    props.onNavigationGuardChange({
      pendingCount: Object.keys(pendingSelections).length,
      save: saveSelections,
      discard: () => setPendingSelections({}),
    })
    return () => props.onNavigationGuardChange(null)
  }, [pendingSelections])

  const refreshRecycleSummary = async () => {
    setRecycleSummary(await api.getRecycleBinSummary())
  }

  const loadRecycle = async (nextPage = 1) => {
    setRecycleLoading(true)
    try {
      const [result, summary] = await Promise.all([api.listRecycledFrames(nextPage, 20), api.getRecycleBinSummary()])
      setRecycleItems(result.items)
      setRecyclePage(result.page)
      setRecycleTotal(result.total)
      setRecycleSummary(summary)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载回收站失败')
    } finally {
      setRecycleLoading(false)
    }
  }

  const appendImages = async () => {
    if (!selectedBatchId || appendFiles.length === 0) return
    setAppendUploading(true)
    try {
      const result = await api.appendBatchImages(selectedBatchId, appendFiles)
      setAppendVisible(false)
      setAppendFiles([])
      await loadBatchDetails(selectedBatchId)
      props.refreshDashboard()
      message.success(`已追加 ${result.imported_count} 张图片${result.skipped_count ? `，跳过 ${result.skipped_count} 张重复图片` : ''}`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '追加图片失败')
    } finally {
      setAppendUploading(false)
    }
  }

  const appendVideos = async () => {
    if (!selectedBatchId || appendVideoFiles.length === 0) return
    setAppendVideoUploading(true)
    setAppendVideoProgress(0)
    try {
      const result = await api.appendBatchVideos(
        selectedBatchId,
        appendVideoFiles,
        appendVideoInterval,
        appendVideoQuality,
        setAppendVideoProgress,
      )
      setAppendVideoVisible(false)
      setAppendVideoFiles([])
      props.onJobStarted(result.job_id)
      message.success(`已上传 ${result.uploaded_count} 个视频，正在后台抽帧`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '追加视频失败')
    } finally {
      setAppendVideoUploading(false)
    }
  }

  const trashSelected = () => {
    if (!selectedBatchId) return
    const explicitIds = frames.filter((frame) => selectedFrameNames.includes(frame.filename)).map((frame) => frame.id)
    const count = allMatching ? Math.max(0, pageTotal - excludedFrameIds.length) : explicitIds.length
    if (count === 0) return message.warning('请先选择要移入回收站的图片')
    Modal.confirm({
      title: `移入回收站（${count} 张）`,
      content: recycleTrashConfirmation(count),
      okText: '移入回收站',
      okButtonProps: { danger: true },
      onOk: async () => {
        const result = await api.trashBatchFrames(selectedBatchId, allMatching
          ? { mode: 'all_matching', status: statusFilter === 'all' ? undefined : statusFilter, search, excluded_ids: excludedFrameIds, request_id: createRequestId() }
          : { mode: 'explicit', ids: explicitIds, request_id: createRequestId() })
        setAllMatching(false); setExcludedFrameIds([]); setSelectedFrameNames([]); setSelectionAnchor(null)
        await Promise.all([loadFramePage(selectedBatchId, 1, pageSize, statusFilter, search), refreshRecycleSummary()])
        props.refreshDashboard()
        message.success(`已将 ${result.affected_count} 张图片移入回收站`)
      },
    })
  }

  const restoreFrame = async (id: string) => {
    try {
      await api.restoreRecycledFrames([id])
      await Promise.all([loadRecycle(recyclePage), selectedBatchId ? loadFramePage(selectedBatchId, page, pageSize, statusFilter, search) : Promise.resolve()])
      props.refreshDashboard()
      message.success('图片及原标注已恢复')
    } catch (error) { message.error(error instanceof Error ? error.message : '恢复失败') }
  }

  const purgeFrame = (id: string) => Modal.confirm({
    title: '永久删除图片？', content: recyclePurgeConfirmation(1), okText: '永久删除', okButtonProps: { danger: true },
    onOk: async () => {
      await api.purgeRecycledFrames([id])
      const nextPage = recycleItems.length === 1 && recyclePage > 1 ? recyclePage - 1 : recyclePage
      await loadRecycle(nextPage)
      props.refreshDashboard()
      message.success('图片和原标注已永久删除')
    },
  })

  const purgeExpired = () => Modal.confirm({
    title: '清理已过期内容？', content: '仅永久删除已超过 7 天保留期的图片及原标注，删除后无法恢复。', okText: '清理过期内容', okButtonProps: { danger: true },
    onOk: async () => {
      const result = await api.purgeExpiredRecycledFrames()
      await loadRecycle(1)
      props.refreshDashboard()
      message.success(`已清理 ${result.deleted_count} 张过期图片，释放 ${formatRecycleBytes(result.released_bytes)}`)
    },
  })

  // Annotation Package Export
  const handleExportPackage = async () => {
    if (!selectedBatchId) return
    setPackaging(true)
    try {
      const res = await api.createAnnotationPackage(selectedBatchId)
      setPackageResult(res)
      message.success('标注包打包成功！')
    } catch (e) {
      message.error(e instanceof Error ? e.message : '打包失败')
    } finally {
      setPackaging(false)
    }
  }

  // Annotation Import & Release
  const handleImportSubmit = async (values: any) => {
    if (!annotationZip) return message.warning('请选择 Roboflow 导出的 ZIP 文件')
    try {
      setUploadingAnnotations(true)
      setAnnotationUploadProgress(0)
      const res = await api.uploadAnnotations(
        values.task_id,
        annotationZip,
        values.project,
        values.provider_version,
        setAnnotationUploadProgress,
      )
      setImportedId(res.import_id)
      setImportVisible(false)
      setAnnotationZip(null)
      importForm.resetFields()
      message.success(`安全导入成功！包含 ${res.sample_count} 个样本`)
      props.refreshDashboard()
    } catch (e) {
      Modal.error({
        title: '标注回导校验失败',
        content: e instanceof Error ? e.message : '未知错误',
      })
    } finally {
      setUploadingAnnotations(false)
      setAnnotationUploadProgress(0)
    }
  }

  const handleReleaseSubmit = async (values: any) => {
    try {
      const res = await api.releaseDataset(
        values.task_id,
        values.annotation_import_id,
        values.display_name,
        values.version
      )
      setReleaseVisible(false)
      releaseForm.resetFields()
      setImportedId(null)
      message.success(`数据集版本 v${values.version} 发布成功！已挂载 DVC`)
      props.refreshDashboard()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '数据集发布失败')
    }
  }

  return (
    <div className="stack interactive-panel">
      <Card className="step-card">
        <div className="review-batch-picker">
          <span>选择要筛选的抽帧批次:</span>
          <Select
            style={{ width: 300 }}
            value={selectedBatchId}
            onChange={requestBatchChange}
            options={batches.map((b) => ({ label: `${b.id} (${b.collection_id})`, value: b.id }))}
            placeholder="无可用抽帧批次，请先启动抽帧"
          />
          <Tooltip title="刷新批次列表"><Button icon={<RefreshCw size={14} />} onClick={loadBatchesList} /></Tooltip>
        </div>
      </Card>

      {selectedBatchId && (
        <Card className="review-batch-workspace">
          <div className="review-batch-summary">
            <div className="review-batch-identity">
              <span>当前抽帧批次</span>
              <h3 title={selectedBatchId}>{selectedBatchId}</h3>
            </div>
            <div className="review-batch-metrics" aria-label="批次筛选统计">
              <div><span>总帧数</span><strong>{stats.total}</strong></div>
              <div className="selected"><span>已保留</span><strong>{stats.selected}</strong></div>
              <div className="rejected"><span>已拒绝</span><strong>{stats.rejected}</strong></div>
              <div><span>待筛选</span><strong>{stats.candidate}</strong></div>
            </div>
          </div>
          <div className="review-batch-actions">
            <div className="review-primary-actions">
              <Button icon={<Upload size={15} />} onClick={() => { setAppendFiles([]); setAppendVisible(true) }}>追加图片</Button>
              <Button icon={<Video size={15} />} onClick={() => { setAppendVideoFiles([]); setAppendVideoProgress(0); setAppendVideoVisible(true) }}>追加视频抽帧</Button>
              <Button icon={<FolderArchive size={15} />} onClick={() => { setRecycleOpen(true); void loadRecycle(1) }}>回收站（{recycleSummary.item_count}）</Button>
              <Button icon={<PencilRuler size={15} />} disabled={stats.selected === 0} onClick={() => props.onNavigate('annotation')}>进入原生标注</Button>
              <Button
                type="primary"
                onClick={() => void saveSelections().catch(() => undefined)}
                loading={submitting}
                disabled={Object.keys(pendingSelections).length === 0}
              >
                保存本地筛选并同步 DB ({Object.keys(pendingSelections).length})
              </Button>
            </div>
            <div className="review-batch-danger-actions">
              <Button danger icon={<Trash2 size={15} />} disabled={!allMatching && selectedFrameNames.length === 0} onClick={trashSelected}>移入回收站</Button>
              <Dropdown menu={{ items: [
                { key: 'delete-record', danger: true, label: '删除批次记录（保留文件）', onClick: () => selectedBatchId && Modal.confirm({ title:'删除抽帧批次？', content:'关联的帧记录和原生标注会一并删除，文件将保留。', okButtonProps:{danger:true}, onOk:async()=>{try{await api.deleteFrameBatch(selectedBatchId,false);setSelectedBatchId(null);setFrames([]);await loadBatchesList();props.refreshDashboard();message.success('抽帧批次已删除')}catch(error){message.error(error instanceof Error?error.message:'删除批次失败');throw error}} }) },
                { key: 'delete-artifacts', danger: true, label: '永久删除批次和文件', onClick: () => selectedBatchId && Modal.confirm({ title:'永久删除抽帧批次？', content:'抽帧图片、帧记录和原生标注都会被永久删除。', okButtonProps:{danger:true}, onOk:async()=>{try{await api.deleteFrameBatch(selectedBatchId,true);setSelectedBatchId(null);setFrames([]);await loadBatchesList();props.refreshDashboard();message.success('抽帧批次和文件已删除')}catch(error){message.error(error instanceof Error?error.message:'删除批次失败');throw error}} }) },
              ] }}>
                <Button danger icon={<MoreHorizontal size={16} />}>批次管理</Button>
              </Dropdown>
            </div>
          </div>

          <Tabs defaultActiveKey="frames" items={[
            {
              key: 'duplicates',
              label: `近重复去重 (${duplicates.length} 组)`,
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    message="近重复哈希提示"
                    description="系统根据 pHash 感知哈希计算出高度重复的候选帧。建议保留主帧（Canonical），并将其他副本（Duplicates）批量判定为重复。"
                    action={<Button size="small" type="primary" onClick={handleQuickMarkDuplicates}>一键标记所有重复帧</Button>}
                    style={{ marginBottom: 16 }}
                  />
                  {duplicates.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未发现近重复图片" />
                  ) : (
                    <div className="duplicate-groups">
                      {duplicates.map((group, idx) => (
                        <div className="duplicate-group" key={idx}>
                          <div className="duplicate-group-header">
                            <span>去重组 #{idx + 1}</span>
                            <Tag color="warning">发现 {group.duplicates.length} 个近重复副本</Tag>
                          </div>
                          <div className="duplicate-group-grid">
                            <div className="duplicate-card">
                              <Card hoverable cover={<img alt="main" className="image-card-img" src={api.getFrameAssetUrl(group.canonical)} />}>
                                <Card.Meta title="主帧 (保留)" description={group.canonical.split('/').pop()} />
                              </Card>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', color: '#c5c5c5' }}>
                              <ArrowRight size={24} />
                            </div>
                            {group.duplicates.map((dupPath, dupIdx) => {
                              const dupFilename = dupPath.split('/').pop() ?? ''
                              const currentStatus = pendingSelections[dupFilename] ?? 'candidate'
                              return (
                                <div className="duplicate-card" key={dupIdx}>
                                  <Card
                                    hoverable
                                    cover={<img alt="dup" className="image-card-img" src={api.getFrameAssetUrl(dupPath)} />}
                                    actions={[
                                      currentStatus === 'rejected/duplicate' ? (
                                        <Button size="small" type="dashed" danger onClick={() => changeStatus(dupFilename, 'candidate')}>
                                          取消标记
                                        </Button>
                                      ) : (
                                        <Button size="small" danger onClick={() => changeStatus(dupFilename, 'rejected/duplicate')}>
                                          标为重复
                                        </Button>
                                      )
                                    ]}
                                    style={{
                                      borderColor: currentStatus === 'rejected/duplicate' ? '#986018' : undefined,
                                      borderWidth: currentStatus === 'rejected/duplicate' ? 2 : 1,
                                    }}
                                  >
                                    <Card.Meta title="重复帧" description={dupFilename} />
                                    {currentStatus === 'rejected/duplicate' && (
                                      <div className="image-badge duplicate">重复帧</div>
                                    )}
                                  </Card>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            },
            {
              key: 'frames',
              label: `图片微调网格 (${frames.length})`,
              children: (
                <div>
                  {loading ? (
                    <Skeleton active />
                  ) : (
                    <>
                      <div className="bulk-review-toolbar">
                        <div className="bulk-review-group">
                          <Select<ReviewStatusFilter> value={statusFilter} onChange={(value) => { setStatusFilter(value); setAllMatching(false); setExcludedFrameIds([]); if (selectedBatchId) void loadFramePage(selectedBatchId, 1, pageSize, value, search) }} options={[
                            { label: `全部 (${stats.total})`, value: 'all' },
                            { label: `待筛选 (${stats.candidate})`, value: 'candidate' },
                            { label: `已保留 (${stats.selected})`, value: 'selected' },
                            { label: `已拒绝 (${stats.rejected})`, value: 'rejected' },
                          ]} />
                          <Button onClick={() => setSelectedFrameNames((current) => [...new Set([...current, ...visibleFrameNames])])}>全选当前页 ({visibleFrameNames.length})</Button>
                          <Button disabled={pageTotal === 0} onClick={() => { setAllMatching(true); setSelectedFrameNames([]); setExcludedFrameIds([]) }}>选择全部匹配 ({pageTotal})</Button>
                          <Button disabled={!allMatching && selectedFrameNames.length === 0} onClick={() => { setAllMatching(false); setExcludedFrameIds([]); setSelectedFrameNames([]); setSelectionAnchor(null) }}>清空选择</Button>
                        </div>
                        <div className="bulk-review-group">
                          <Input.Search value={searchInput} placeholder="搜索文件名" onChange={(event) => setSearchInput(event.target.value)} onSearch={(value) => { setSearch(value); setAllMatching(false); if (selectedBatchId) void loadFramePage(selectedBatchId, 1, pageSize, statusFilter, value) }} style={{ width: 190 }} />
                          <span>{allMatching ? <>已选择全部匹配 <strong>{Math.max(0, pageTotal - excludedFrameIds.length)}</strong> 张</> : <>已选择 <strong>{selectedFrameNames.length}</strong> 张</>} · 待同步 <strong>{Object.keys(pendingSelections).length}</strong> 项</span>
                          <Select placeholder="批量设置状态" disabled={!allMatching && selectedFrameNames.length === 0} value={undefined} onChange={applySelectedStatus} options={bulkStatusOptions} />
                        </div>
                      </div>
                      <div className="image-grid">
                      {visibleFrames.map((frame) => {
                        const status = effectiveFrameStatus(frame, pendingSelections)
                        const imageSrc = api.getFrameAssetUrl(frame.stored_path)
                        const checked = allMatching ? !excludedFrameIds.includes(frame.id) : selectedFrameNames.includes(frame.filename)

                        return (
                          <div className={`image-card ${status.startsWith('rejected') ? 'rejected' : status === 'selected' ? 'selected' : ''} ${checked ? 'bulk-selected' : ''}`} key={frame.id} onClick={(event) => { if (!(event.target as HTMLElement).closest('.ant-select')) toggleFrameSelection(frame.filename, event.shiftKey) }}>
                            <label className="image-select-checkbox" onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={checked} readOnly onClick={(event) => toggleFrameSelection(frame.filename, event.shiftKey)} /><span>选择</span></label>
                            <img alt={frame.filename} className="image-card-img" src={imageSrc} />

                            {/* Visual status badge */}
                            {status === 'selected' && <div className="image-badge selected">{reviewStatusLabel(status)}</div>}
                            {status.startsWith('rejected') && <div className="image-badge rejected">{reviewStatusLabel(status)}</div>}
                            {status === 'candidate' && <div className="image-badge candidate">{reviewStatusLabel(status)}</div>}

                            <div className="image-card-body">
                              <span className="image-card-title">{frame.filename}</span>
                              <div className="image-card-meta">
                                <span>Idx: {frame.frame_index}</span>
                                <span>{(frame.timestamp_ms / 1000).toFixed(1)}s</span>
                              </div>
                              <div className="image-card-actions">
                                <Select
                                  size="small"
                                  style={{ width: '100%' }}
                                  value={status}
                                  onChange={(val) => changeStatus(frame.filename, val)}
                                  options={bulkStatusOptions}
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className="frame-pagination"><Pagination current={page} pageSize={pageSize} total={pageTotal} showSizeChanger pageSizeOptions={[30, 60, 120]} showTotal={(total) => `共 ${total} 张`} onChange={(nextPage, nextSize) => { if (selectedBatchId) void loadFramePage(selectedBatchId, nextPage, nextSize, statusFilter, search) }} /></div>
                    </>
                  )}
                </div>
              )
            },
            {
              key: 'packaging',
              label: '标注与发布控制台',
              children: (
                <Row gutter={[20, 20]}>
                  <Col span={12}>
                    <Card title="第1步: 导出并下载 Roboflow 标注包" style={{ height: '100%' }}>
                      <p>将当前标记为“已保留”的图片及关系清单生成标注包 ZIP，下载后可直接上传至 Roboflow。</p>
                      <Button type="primary" icon={<Download size={14} />} onClick={handleExportPackage} loading={packaging}>
                        导出 ZIP 标注包
                      </Button>

                      {packageResult && (
                        <div style={{ marginTop: 16, padding: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4 }}>
                          <div><strong>SHA-256:</strong> <code style={{ fontSize: 11 }}>{packageResult.sha256}</code></div>
                          <div style={{ marginTop: 8 }}>
                            <Button type="dashed" size="small" href={api.getAnnotationPackageUrl(selectedBatchId)}>
                              下载标注 ZIP ({selectedBatchId}.zip)
                            </Button>
                          </div>
                        </div>
                      )}
                    </Card>
                  </Col>

                  <Col span={12}>
                    <Card title="第2步: 回导 Roboflow 标注 ZIP" style={{ height: '100%' }}>
                      <p>完成 Roboflow 标注后，下载对应的 YOLO 分割/检测压缩包，在下方进行安全解压与数据格式严格校验。</p>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Button type="primary" icon={<Upload size={14} />} onClick={() => {
                          importForm.setFieldsValue({
                            task_id: props.tasks[0]?.id,
                            project: props.tasks[0]?.id,
                            provider_version: '1'
                          })
                          setImportVisible(true)
                        }}>
                          导入标注 ZIP 包
                        </Button>

                        {importedId && (
                          <div style={{ marginTop: 16, padding: 12, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 4 }}>
                            <Alert type="success" showIcon message="标注已安全载入" description={`Import ID: ${importedId}`} style={{ marginBottom: 12 }} />
                            <Button type="primary" onClick={() => {
                              releaseForm.setFieldsValue({
                                task_id: props.tasks[0]?.id,
                                annotation_import_id: importedId,
                                display_name: `${props.tasks[0]?.id ?? ''} 数据集`,
                                version: '1.0.0'
                              })
                              setReleaseVisible(true)
                            }}>
                              发布不可变数据集
                            </Button>
                          </div>
                        )}
                      </Space>
                    </Card>
                  </Col>
                </Row>
              )
            }
          ]} />
        </Card>
      )}

      <Modal title={`向批次 ${selectedBatchId ?? ''} 追加图片`} open={appendVisible} confirmLoading={appendUploading} okText="上传并追加" okButtonProps={{ disabled: appendFiles.length === 0 }} onOk={() => void appendImages()} onCancel={() => { if (!appendUploading) { setAppendVisible(false); setAppendFiles([]) } }} maskClosable={!appendUploading}>
        <AntUpload.Dragger multiple accept=".jpg,.jpeg,.png,.bmp,.webp" beforeUpload={() => false} fileList={appendFiles.map((file, index) => ({ uid: `${index}-${file.name}`, name: file.name, status: 'done', originFileObj: file } as any))} onChange={({ fileList }) => { const files = fileList.map((item) => item.originFileObj).filter(Boolean) as File[]; const error = uploadLimitError(files, 'image'); if (error) message.error(error); else setAppendFiles(files) }} onRemove={(file) => { setAppendFiles((items) => items.filter((item) => item.name !== file.name)); return true }} disabled={appendUploading}>
          <p className="ant-upload-drag-icon"><Images size={38} /></p><p>拖入图片或点击选择</p><p className="ant-upload-hint">{IMAGE_UPLOAD_GUIDANCE}；重复内容会自动跳过</p>
        </AntUpload.Dragger>
        <Alert type="info" showIcon message="追加图片会记录为手动上传来源" description="手动图片不继承视频时间戳；原视频帧、抽帧参数和来源分组保持不变。" style={{ marginTop: 16 }} />
      </Modal>

      <Modal
        title={`向批次 ${selectedBatchId ?? ''} 追加视频抽帧`}
        open={appendVideoVisible}
        confirmLoading={appendVideoUploading}
        okText={appendVideoUploading ? `正在上传 ${appendVideoProgress}%` : '上传并开始抽帧'}
        okButtonProps={{ disabled: appendVideoFiles.length === 0 }}
        closable={!appendVideoUploading}
        maskClosable={!appendVideoUploading}
        onOk={() => void appendVideos()}
        onCancel={() => { if (!appendVideoUploading) { setAppendVideoVisible(false); setAppendVideoFiles([]); setAppendVideoProgress(0) } }}
      >
        <AntUpload.Dragger
          multiple
          accept=".mp4,.avi,.mov,.mkv,.wmv,.flv,.webm,.m4v"
          beforeUpload={() => false}
          fileList={appendVideoFiles.map((file, index) => ({ uid: `${index}-${file.name}`, name: file.name, status: 'done', originFileObj: file } as any))}
          onChange={({ fileList }) => {
            const files = fileList.map((item) => item.originFileObj).filter(Boolean) as File[]
            const error = uploadLimitError(files, 'video')
            if (error) message.error(error)
            else setAppendVideoFiles(files)
          }}
          onRemove={(file) => { setAppendVideoFiles((items) => items.filter((item) => item.name !== file.name)); return true }}
          disabled={appendVideoUploading}
        >
          <p className="ant-upload-drag-icon"><Video size={38} /></p>
          <p>拖入视频或点击选择</p>
          <p className="ant-upload-hint">只抽取本次上传且内容不重复的视频；文件会上传到云端受管目录</p>
        </AntUpload.Dragger>
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={12}>
            <label>抽帧间隔（秒）</label>
            <InputNumber min={0.1} step={0.1} value={appendVideoInterval} onChange={(value) => setAppendVideoInterval(value ?? 1)} style={{ width: '100%', marginTop: 6 }} disabled={appendVideoUploading} />
          </Col>
          <Col span={12}>
            <label>JPEG 质量</label>
            <InputNumber min={1} max={100} value={appendVideoQuality} onChange={(value) => setAppendVideoQuality(value ?? 95)} style={{ width: '100%', marginTop: 6 }} disabled={appendVideoUploading} />
          </Col>
        </Row>
        {appendVideoUploading && <Progress percent={appendVideoProgress} size="small" style={{ marginTop: 16 }} />}
        <Alert
          type="info"
          showIcon
          message="新抽取图片默认进入待筛选状态"
          description="已有图片、筛选状态和标注保持不变；已经发布的数据集版本不会自动改变。"
          style={{ marginTop: 16 }}
        />
      </Modal>

      <Drawer title={`图片回收站（${recycleSummary.item_count}）`} width="min(920px, 94vw)" open={recycleOpen} onClose={() => setRecycleOpen(false)} extra={<Button danger disabled={!recycleSummary.item_count} onClick={purgeExpired}>清理过期内容</Button>}>
        <Alert type="info" showIcon message="图片与原标注保留 7 天" description={`当前占用 ${formatRecycleBytes(recycleSummary.total_bytes)}。恢复后回到原批次；永久删除不会影响已经发布的不可变数据集版本。`} style={{ marginBottom: 16 }} />
        <Table<RecycledFrameSummary> rowKey="id" loading={recycleLoading} dataSource={recycleItems} pagination={false} size="small" scroll={{ x: 760 }} columns={[
          { title: '预览', width: 92, render: (_, item) => <img className="recycle-thumbnail" src={api.getFrameAssetUrl(item.stored_path)} alt={item.filename} loading="lazy" /> },
          { title: '图片', dataIndex: 'filename', ellipsis: true, render: (value, item) => <div><strong>{value}</strong><div className="muted">原批次：{item.batch_id}</div></div> },
          { title: '原标注', dataIndex: 'has_annotation', width: 90, render: (value) => value ? <Tag color="green">已保留</Tag> : <Tag>无</Tag> },
          { title: '大小', dataIndex: 'size_bytes', width: 85, render: formatRecycleBytes },
          { title: '自动清理时间', dataIndex: 'purge_after', width: 150, render: formatRecycleExpiry },
          { title: '操作', width: 145, fixed: 'right', render: (_, item) => <Space><Button size="small" onClick={() => void restoreFrame(item.id)}>恢复</Button><Button size="small" danger onClick={() => purgeFrame(item.id)}>永久删除</Button></Space> },
        ]} />
        {recycleTotal > 0 && <div className="frame-pagination"><Pagination current={recyclePage} pageSize={20} total={recycleTotal} showSizeChanger={false} showTotal={(total) => `共 ${total} 张`} onChange={(nextPage) => void loadRecycle(nextPage)} /></div>}
      </Drawer>

      {/* Import annotations Modal */}
      <Modal
        title="导入 Roboflow 标注 ZIP 归档"
        open={importVisible}
        confirmLoading={uploadingAnnotations}
        okText={uploadingAnnotations ? (annotationUploadProgress >= 100 ? '服务器正在解压与校验' : `正在上传 ${annotationUploadProgress}%`) : '上传并校验'}
        okButtonProps={{ disabled: !annotationZip }}
        closable={!uploadingAnnotations}
        maskClosable={!uploadingAnnotations}
        onCancel={() => { if (!uploadingAnnotations) { setImportVisible(false); setAnnotationZip(null); setAnnotationUploadProgress(0); importForm.resetFields() } }}
        onOk={() => importForm.submit()}
        destroyOnHidden
      >
        <Form form={importForm} layout="vertical" onFinish={handleImportSubmit}>
          <Form.Item name="task_id" label="所绑定的业务任务 ID" rules={[{ required: true, message: '请选择关联任务' }]}>
            <Select placeholder="选择绑定的任务契约">
              {props.tasks.map((t) => (
                <Select.Option key={t.id} value={t.id}>{t.id}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="Roboflow 标注 ZIP" extra="单个 ZIP 作为一次请求上传，总大小不得超过网关 20 GB 限制；上传前请确认服务器有足够剩余磁盘空间。" required>
            <AntUpload.Dragger
              accept=".zip,application/zip"
              maxCount={1}
              beforeUpload={(file) => { const error = uploadLimitError([file], 'archive'); if (error) { message.error(error); return AntUpload.LIST_IGNORE } setAnnotationZip(file); return false }}
              onRemove={() => { setAnnotationZip(null); return true }}
              fileList={annotationZip ? [annotationZip as any] : []}
              disabled={uploadingAnnotations}
            >
              <p><Upload size={24} /></p>
              <p>点击或拖拽 ZIP 文件到这里</p>
            </AntUpload.Dragger>
            {uploadingAnnotations && <Progress percent={annotationUploadProgress} size="small" style={{ marginTop: 12 }} />}
            {uploadingAnnotations && annotationUploadProgress >= 100 && <Alert type="info" showIcon message="文件传输完成，服务器正在解压并校验图片、标签和标注几何" style={{ marginTop: 12 }} />}
          </Form.Item>
          <Form.Item name="project" label="Roboflow 项目名称 (Project Name)" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="例如: signal-light-segmentation" />
          </Form.Item>
          <Form.Item name="provider_version" label="Roboflow 项目导出版号 (Version)" rules={[{ required: true, message: '请输入版本号' }]}>
            <Input placeholder="例如: 1" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Release Dataset Modal */}
      <Modal
        title="发布不可变数据集版本"
        open={releaseVisible}
        onCancel={() => setReleaseVisible(false)}
        onOk={() => releaseForm.submit()}
      >
        <Form form={releaseForm} layout="vertical" onFinish={handleReleaseSubmit}>
          <Form.Item name="task_id" label="所绑定的业务任务 ID" rules={[{ required: true, message: '请选择关联任务' }]}>
            <Select placeholder="选择关联的任务契约">
              {props.tasks.map((t) => (
                <Select.Option key={t.id} value={t.id}>{t.id}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="annotation_import_id" label="绑定的标注导入 ID (Annotation Import ID)">
            <Input disabled />
          </Form.Item>
          <Form.Item name="display_name" label="数据集名称" rules={[{ required: true, whitespace: true, message: '请输入数据集名称' }, { max: 200, message: '数据集名称不能超过 200 个字符' }]}>
            <Input showCount maxLength={200} placeholder="例如：电梯标识分割数据集" />
          </Form.Item>
          <Form.Item name="version" label="要发布的数据集版本号 (Semantic Version)" rules={[{ required: true, message: '请输入数据集版本' }]}>
            <Input placeholder="例如: 1.0.0" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function DatasetWorkspace({ data, tasks, refreshDashboard }: { data: DatasetReleaseSummary[]; tasks: TaskSummary[]; refreshDashboard: () => void }) {
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploadForm] = Form.useForm<{ task_id: string; batch_id: string }>()
  const [browseRelease, setBrowseRelease] = useState<DatasetReleaseSummary>()
  const [releaseImages, setReleaseImages] = useState<Array<{ path: string; name: string; size_bytes: number }>>([])
  const [browsing, setBrowsing] = useState(false)

  const browse = async (release: DatasetReleaseSummary) => {
    setBrowseRelease(release); setBrowsing(true)
    try { setReleaseImages(await api.listDatasetReleaseImages(release.id)) } catch (error) { message.error(error instanceof Error ? error.message : '加载数据集图片失败') } finally { setBrowsing(false) }
  }
  const upload = async () => {
    try {
      const values = await uploadForm.validateFields()
      if (!uploadFiles.length) return message.warning('请选择至少一张图片')
      setUploading(true)
      const result = await api.uploadImages(values.task_id, values.batch_id, uploadFiles)
      setUploadOpen(false); setUploadFiles([]); uploadForm.resetFields(); refreshDashboard()
      message.success(`已上传 ${result.imported_count} 张图片，可在数据筛选或原生标注中查看`)
    } catch (error) { message.error(error instanceof Error ? error.message : '图片上传失败') } finally { setUploading(false) }
  }

  return <div className="stack">
    <section className="panel table-panel"><div className="panel-heading"><div><h2>数据集版本</h2><p>浏览不可变发布版本，或上传新图片进入待标注流程</p></div><Button type="primary" icon={<Upload size={15} />} onClick={() => setUploadOpen(true)}>上传图片</Button></div><ReleasesTable data={data} compact refreshDashboard={refreshDashboard} onBrowse={browse} /></section>
    <Modal title="上传待标注图片" open={uploadOpen} confirmLoading={uploading} onCancel={() => setUploadOpen(false)} onOk={() => void upload()} okText="上传并进入标注队列" width={620}>
      <Form form={uploadForm} layout="vertical" initialValues={{ batch_id: `images-${dayjs().format('YYYYMMDD-HHmm')}` }}>
        <Form.Item name="task_id" label="业务任务" rules={[{ required: true }]}><Select options={tasks.map((task) => ({ value: task.id, label: `${task.id} · ${task.task_type}` }))} /></Form.Item>
        <Form.Item name="batch_id" label="图片批次 ID" rules={[{ required: true }]}><Input /></Form.Item>
        <AntUpload.Dragger multiple accept=".jpg,.jpeg,.png,.bmp,.webp" beforeUpload={() => false} fileList={uploadFiles.map((file, index) => ({ uid: `${index}-${file.name}`, name: file.name, status: 'done', originFileObj: file } as any))} onChange={({ fileList }) => { const files = fileList.map((item) => item.originFileObj).filter(Boolean) as File[]; const error = uploadLimitError(files, 'image'); if (error) message.error(error); else setUploadFiles(files) }} onRemove={(file) => { setUploadFiles((items) => items.filter((item) => item.name !== file.name)); return true }}><p className="ant-upload-drag-icon"><Images size={38} /></p><p>拖入图片或点击选择</p><p className="ant-upload-hint">{IMAGE_UPLOAD_GUIDANCE}</p></AntUpload.Dragger>
      </Form>
    </Modal>
    <Modal title={browseRelease ? `${formatDatasetReleaseLabel(browseRelease)} · ${releaseImages.length} 张图片` : '数据集图片'} open={Boolean(browseRelease)} footer={null} width="min(1100px, 92vw)" onCancel={() => { setBrowseRelease(undefined); setReleaseImages([]) }}>
      {browsing ? <Spin /> : releaseImages.length === 0 ? <Empty description="该版本未发现图片" /> : <div className="dataset-image-grid">{releaseImages.map((image) => <a key={image.path} href={api.getDatasetReleaseImageUrl(browseRelease!.id, image.path)} target="_blank" rel="noreferrer"><img src={api.getDatasetReleaseImageUrl(browseRelease!.id, image.path)} alt={image.name} loading="lazy" /><span>{image.name}</span><small>{formatBytes(image.size_bytes)}</small></a>)}</div>}
    </Modal>
  </div>
}

function ReleasesTable({ data, compact = false, refreshDashboard, onBrowse }: { data: DatasetReleaseSummary[]; compact?: boolean; refreshDashboard?: () => void; onBrowse?: (release: DatasetReleaseSummary) => void }) {
  const isMobile = useMobileViewport()
  const deleteRelease = (record: DatasetReleaseSummary, mode: 'record' | 'artifacts' | 'cascade') => {
    const cascade = mode === 'cascade'
    const deleteArtifacts = mode !== 'record'
    Modal.confirm({
      title: cascade ? '级联删除整个数据链路？' : deleteArtifacts ? '永久删除数据集版本？' : '删除数据集版本？',
      content: cascade ? '将永久删除该数据集及其训练、模型、推理历史和全部产物。此操作不可恢复。' : deleteArtifacts ? '数据集发布目录会被永久清理；存在下游引用时操作会被阻止。' : '被训练或模型引用时会拒绝删除。',
      okText: cascade ? '确认级联删除' : '确认删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteDatasetRelease(record.id, deleteArtifacts, cascade)
          refreshDashboard?.()
          message.success(cascade ? '数据集及全部下游已删除' : deleteArtifacts ? '数据集版本和文件已删除' : '数据集版本已删除')
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除版本失败')
          throw error
        }
      },
    })
  }
  const columns: ColumnsType<DatasetReleaseSummary> = [
    { title: '数据集名称', dataIndex: 'display_name', render: (value, record) => <strong>{value || record.task_id}</strong> },
    { title: '版本', dataIndex: 'version', render: (value) => <strong>v{value}</strong> },
    { title: '任务', dataIndex: 'task_id' },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={value === 'published' ? 'green' : 'orange'}>{value}</Tag> },
    { title: '数据划分', key: 'split', render: (_, record) => <span className="release-split-summary">{formatReleaseSplit(record)}</span> },
    ...(!compact ? [{ title: '路径', dataIndex: 'release_path', ellipsis: true }] : []),
    { title: '发布时间', dataIndex: 'created_at', render: (value) => dayjs(value).format('YYYY-MM-DD') },
    ...((!compact || onBrowse) ? [{ title: '操作', key: 'actions', render: (_: unknown, record: DatasetReleaseSummary) => <Space>{onBrowse && <Button size="small" icon={<Eye size={13} />} onClick={() => onBrowse(record)}>查看图片</Button>}<Tooltip title="删除版本记录，保留数据文件"><Button danger size="small" icon={<Trash2 size={13} />} onClick={() => Modal.confirm({ title:'删除数据集版本？', content:'被训练或模型引用时会拒绝删除。', okButtonProps:{danger:true}, onOk:async()=>{try{await api.deleteDatasetRelease(record.id,false);refreshDashboard?.();message.success('数据集版本已删除')}catch(error){message.error(error instanceof Error?error.message:'删除版本失败');throw error}} })} /></Tooltip><Tooltip title="删除版本并清理发布目录"><Button danger size="small" icon={<Trash2 size={13} />} onClick={() => Modal.confirm({ title:'永久删除数据集版本？', content:'数据集发布目录会被永久清理；存在下游引用时操作会被阻止。', okButtonProps:{danger:true}, onOk:async()=>{try{await api.deleteDatasetRelease(record.id,true);refreshDashboard?.();message.success('数据集版本和文件已删除')}catch(error){message.error(error instanceof Error?error.message:'删除版本失败');throw error}} })} /></Tooltip><Tooltip title="删除数据集、训练、模型、推理历史和全部产物"><Button danger size="small" type="primary" icon={<Trash2 size={13} />} onClick={() => Modal.confirm({ title:'级联删除整个数据链路？', content:'将永久删除该数据集及其训练、模型、推理历史和全部产物。此操作不可恢复。', okText:'确认级联删除', okButtonProps:{danger:true}, onOk:async()=>{try{await api.deleteDatasetRelease(record.id,true,true);refreshDashboard?.();message.success('数据集及全部下游已删除')}catch(error){message.error(error instanceof Error?error.message:'级联删除失败');throw error}} })} /></Tooltip></Space> }] : []),
  ]
  const table = isMobile ? <div className="mobile-release-list mobile-record-list">{data.map((release) => <MobileRecordCard
    key={release.id}
    title={release.display_name || release.task_id}
    subtitle={`v${release.version} · ${release.task_id}`}
    status={<Tag color={release.status === 'published' ? 'green' : 'orange'}>{release.status}</Tag>}
    metadata={[["数据划分", formatReleaseSplit(release)], ["发布时间", dayjs(release.created_at).format('YYYY-MM-DD')]]}
    metric={release.release_path}
    onClick={() => onBrowse?.(release)}
    actions={<><Button size="small" icon={<Eye size={13} />} disabled={!onBrowse} onClick={() => onBrowse?.(release)}>查看图片</Button><Dropdown trigger={['click']} menu={{ items: [{ key: 'record', label: '删除版本记录', danger: true }, { key: 'artifacts', label: '删除版本和目录', danger: true }, { key: 'cascade', label: '级联删除全部下游', danger: true }], onClick: ({ key }) => deleteRelease(release, key as 'record' | 'artifacts' | 'cascade') }}><Button size="small" danger icon={<MoreHorizontal size={13} />}>删除与清理</Button></Dropdown></>}
  />)}</div> : <Table rowKey="id" size={compact ? 'small' : 'middle'} columns={columns} dataSource={data} pagination={false} />
  return compact ? table : <DataPanel title="数据集版本" subtitle="校验、校验和与 DVC 状态">{table}</DataPanel>
}

function SystemView({ health }: { health: HealthStatus | null }) {
  return (
    <div className="panel system-panel">
      <div className="system-indicator"><Server size={28} /><span /></div>
      <div>
        <h2>数据服务</h2>
        <Tag color={health?.status === 'ok' ? 'green' : 'red'}>{health?.status ?? 'unknown'}</Tag>
        <dl>
          <dt>存储根目录</dt>
          <dd>{health?.storage_root ?? '-'}</dd>
          <dt>访问模式</dt>
          <dd>单实例数据管理工作台</dd>
          <dt>服务 API</dt>
          <dd>{`${window.location.origin}/api`}</dd>
          <dt>开源许可</dt>
          <dd><a href="https://github.com/idCntrue/TrainForge" target="_blank" rel="noreferrer">AGPL-3.0 · 查看对应源码</a></dd>
        </dl>
      </div>
    </div>
  )
}

function DataPanel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="panel table-panel"><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{children}</section>
}

export default App
