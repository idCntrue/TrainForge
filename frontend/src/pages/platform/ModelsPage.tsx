import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Descriptions, Drawer, Dropdown, message, Modal, Select, Space, Table, Tooltip } from 'antd'
import { Archive, Box, CheckCircle2, Copy, Download, FileCode2, MoreHorizontal, Play, Send, ShieldCheck } from 'lucide-react'

import { api } from '../../api'
import type { ModelGateReportApiResponse, ModelGateRunApiResponse } from '../../api'
import { MetricStrip } from '../../components/platform/MetricStrip'
import { PageHeader } from '../../components/platform/PageHeader'
import { StatusTag } from '../../components/platform/StatusTag'
import { TaskTag } from '../../components/platform/TaskTag'
import { mapModel } from '../../platform/apiPlatformRepository'
import { platformRepository } from '../../platform/repository'
import type { ModelArtifact, ModelStatus, TaskType } from '../../platform/types'
import { createOperationGate } from './modelOperationGate'
import { publicationPresentation } from './modelsPresentation'
import { MobileRecordCard } from '../../components/mobile/MobileRecordCard'
import { useMobileViewport } from '../../responsive/useMobileViewport'
import { ModelGateDiagnosticsPanel } from './ModelGateDiagnosticsPanel'
import { gateCompletionFeedback } from './modelGateDiagnostics'
import { formatGateBytes, ModelGateHistoryPanel } from './ModelGateHistoryPanel'

export default function ModelsPage() {
  const isMobile = useMobileViewport()
  const [models, setModels] = useState<ModelArtifact[]>([]), [selected, setSelected] = useState<ModelArtifact>(), [busy, setBusy] = useState(false)
  const [gateReport, setGateReport] = useState<ModelGateReportApiResponse>(), [gateReportLoading, setGateReportLoading] = useState(false)
  const [gateRuns, setGateRuns] = useState<ModelGateRunApiResponse[]>([]), [gateRunsLoading, setGateRunsLoading] = useState(false)
  const operationGate = useRef(createOperationGate())
  const [task, setTask] = useState<TaskType>(), [status, setStatus] = useState<ModelStatus>()
  const load = useCallback(async () => { const next = await platformRepository.listModels({ task, status }); setModels(next); setSelected((current)=>current ? next.find((item)=>item.id===current.id) ?? current : undefined) }, [task, status])
  useEffect(() => { void load().catch((error)=>message.error(error.message)) }, [load])
  useEffect(() => {
    if (!selected) { setGateReport(undefined); setGateRuns([]); return }
    let active = true
    setGateReport(undefined)
    setGateRuns([])
    setGateReportLoading(true)
    setGateRunsLoading(true)
    void api.getModelGateReport(selected.id)
      .then((report) => { if (active) setGateReport(report) })
      .catch(() => { if (active) message.warning('门禁诊断详情读取失败，可重新运行门禁后再试。') })
      .finally(() => { if (active) setGateReportLoading(false) })
    void api.listModelGateRuns(selected.id)
      .then((runs) => { if (active) setGateRuns(runs) })
      .catch(() => { if (active) message.warning('门禁历史读取失败，请稍后刷新重试。') })
      .finally(() => { if (active) setGateRunsLoading(false) })
    return () => { active = false }
  }, [selected?.id])
  const performAction = async (kind:'gates'|'publish'|'archive') => {
    if (!selected) return
    await operationGate.current.run(async () => {
      try {
        setBusy(true)
        const response = kind === 'gates' ? await api.runModelGates(selected.id) : kind === 'publish' ? await api.publishModel(selected.id) : await api.archiveModel(selected.id)
        const mapped = mapModel(response)
        setSelected(mapped)
        if (kind === 'gates') {
          const [report, runs] = await Promise.all([api.getModelGateReport(mapped.id), api.listModelGateRuns(mapped.id)])
          setGateReport(report)
          setGateRuns(runs)
          const feedback = gateCompletionFeedback(mapped)
          message[feedback.type](feedback.message)
        } else {
          message.success(kind === 'publish' ? '模型已发布' : '模型已归档')
        }
        await load()
      }
      catch (error) { message.error(error instanceof Error ? error.message : '模型操作失败'); await load().catch(() => undefined) } finally { setBusy(false) }
    })
  }
  const action = (kind:'gates'|'publish'|'archive') => {
    if (kind === 'publish' && selected) {
      const presentation = publicationPresentation(selected.qualityReport?.verdict)
      if (presentation.requiresConfirmation) {
        Modal.confirm({
          title: presentation.title,
          content: presentation.consequence,
          okText: '确认承担风险并发布',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: () => performAction('publish'),
        })
        return
      }
    }
    void performAction(kind)
  }
  const deleteModel = (deleteArtifacts: boolean, cascade = false) => {
    if (!selected) return
    Modal.confirm({ title: cascade ? '级联删除模型和推理历史？' : deleteArtifacts ? '删除模型及制品？' : '删除模型记录？', content: cascade ? '将删除该模型、所有关联推理历史和制品；发布状态也不会保留。' : deleteArtifacts ? 'PT、ONNX 和门禁制品会被永久清理。发布模型必须先归档，存在推理历史时不能删除。' : '仅删除模型记录，制品文件保持不变。', okText: cascade ? '确认级联删除' : deleteArtifacts ? '永久删除' : '删除记录', okButtonProps: { danger: true }, onOk: async () => { try { setBusy(true); await api.deleteModel(selected.id, deleteArtifacts, cascade); setSelected(undefined); await load(); message.success(cascade ? '模型及推理历史已删除' : '模型已删除') } catch (error) { message.error(error instanceof Error ? error.message : '删除模型失败'); throw error } finally { setBusy(false) } } })
  }
  const deleteGateRun = async (run: ModelGateRunApiResponse) => {
    if (!selected) return
    try {
      setBusy(true)
      const response = await api.deleteModelGateRun(selected.id, run.id)
      const mapped = mapModel(response.model)
      setSelected(mapped)
      const [report, runs] = await Promise.all([api.getModelGateReport(mapped.id), api.listModelGateRuns(mapped.id)])
      setGateReport(report)
      setGateRuns(runs)
      await load()
      const freed = formatGateBytes(response.deleted_size_bytes)
      message.success(response.fallback_run_id
        ? `已删除本轮门禁并释放 ${freed}，当前已自动切换到 ${response.fallback_run_id}`
        : response.model.gate_report_path
          ? `已删除历史门禁并释放 ${freed}，当前模型不受影响`
          : `已删除最后一轮门禁并释放 ${freed}，模型已恢复为待运行门禁`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '门禁记录删除失败，请稍后重试。')
      throw error
    } finally {
      setBusy(false)
    }
  }
  const exportModel = async () => {
    if (!selected) return
    try {
      setBusy(true)
      const download = await api.downloadModelRelease(selected.id)
      const url = URL.createObjectURL(download.blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = download.filename ?? `${selected.name}-v${selected.version}.zip`
      anchor.click()
      URL.revokeObjectURL(url)
      message.success('发布包已开始下载，内含 PT、ONNX 和类别索引文件')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发布包导出失败')
    } finally { setBusy(false) }
  }
  const published = models.filter((model) => model.status === 'published').length
  const artifactRows = selected ? Object.entries(selected.artifacts).map(([format, artifact]) => ({
    key: `artifact-${format}`,
    label: `${format.toUpperCase()} 制品`,
    children: <div className="model-artifact-details"><span>{artifact.exists ? `${(artifact.sizeBytes / 1024 / 1024).toFixed(1)} MB` : '文件不存在'}</span><Space.Compact className="model-artifact-path-row"><Tooltip title={artifact.path}><code className="model-artifact-path">{artifact.path}</code></Tooltip><Button icon={<Copy size={14} />} title="复制实际路径" onClick={() => void navigator.clipboard.writeText(artifact.path).then(() => message.success('路径已复制'))} /></Space.Compact><small className="model-artifact-hash">SHA-256：{artifact.sha256 || '-'}</small></div>,
  })) : []
  return <div className="platform-stack">
    <PageHeader title="模型中心" description="管理训练产物、独立测试证据、PT/ONNX 一致性门禁和发布状态。" />
    <MetricStrip items={[{ label:'当前模型',value:models.length,icon:Box,tone:'blue' },{ label:'已发布',value:published,icon:ShieldCheck,tone:'green' },{ label:'ONNX 就绪',value:models.filter((model) => model.formats.includes('ONNX')).length,icon:FileCode2,tone:'teal' },{ label:'硬门禁通过',value:models.filter((model) => model.gates.every((gate) => gate.advisory || gate.status === 'passed')).length,icon:CheckCircle2,tone:'amber' }]} />
    <div className="platform-filterbar"><Select allowClear placeholder="全部任务" value={task} onChange={setTask} options={['detect','segment'].map((value) => ({ value, label:value.toUpperCase() }))} /><Select allowClear placeholder="全部发布状态" value={status} onChange={setStatus} options={['candidate','published','blocked','archived'].map((value) => ({ value, label:value }))} /></div>
    <section className="platform-panel">{isMobile ? <div className="mobile-record-list">
      {models.map((model) => <MobileRecordCard
        key={model.id}
        title={`${model.name} v${model.version}`}
        subtitle={model.datasetName}
        status={<StatusTag status={model.status} />}
        metadata={[[model.primaryMetricLabel, model.primaryMetric.toFixed(3)], ['格式', model.formats.join(' / ') || '-']]}
        metric={`${model.sizeMb} MB`}
        onClick={() => setSelected(model)}
      />)}
      {models.length === 0 && <div className="mobile-empty-state">暂无真实模型制品</div>}
    </div> : <Table locale={{ emptyText: '暂无真实模型制品' }} rowKey="id" dataSource={models} onRow={(model) => ({ onClick: () => setSelected(model) })} columns={[
      { title:'模型',render:(_,model)=><div className="table-primary"><strong>{model.name} <small>v{model.version}</small></strong><span>{model.datasetName}</span></div> },
      { title:'任务',dataIndex:'task',render:(value)=><TaskTag task={value} /> },{ title:'状态',dataIndex:'status',render:(value)=><StatusTag status={value} /> },
      { title:'核心指标',render:(_,model)=>`${model.primaryMetricLabel} ${model.primaryMetric.toFixed(3)}` },{ title:'格式',render:(_,model)=>model.formats.join(' / ') || '-' },{ title:'大小',dataIndex:'sizeMb',render:(value)=>`${value} MB` },
    ]} />}</section>
    <Drawer className="mobile-fullscreen-drawer model-detail-drawer" width={isMobile ? '100%' : 'min(920px, calc(100vw - 32px))'} title={selected ? `${selected.name} v${selected.version}` : ''} open={Boolean(selected)} onClose={() => setSelected(undefined)} extra={selected && <Space>{['candidate','blocked'].includes(selected.status) && <Button loading={busy} disabled={busy} icon={<Play size={15}/>} onClick={()=>void action('gates')}>运行门禁</Button>}{selected.status === 'candidate' && selected.gates.every((gate)=>gate.advisory || gate.status==='passed') && <Button loading={busy} disabled={busy} type="primary" icon={<Send size={15}/>} onClick={()=>void action('publish')}>发布</Button>}{selected.status === 'published' && <Button loading={busy} disabled={busy} icon={<Archive size={15}/>} onClick={()=>void action('archive')}>归档</Button>}<Dropdown trigger={['click']} menu={{ items: [...(selected.status !== 'published' ? [{ key:'record',label:'仅删除模型记录' },{ key:'artifacts',label:'删除记录并清理制品',danger:true }] : []),{ key:'cascade',label:'级联删除模型与推理历史',danger:true }], onClick:({key})=>deleteModel(key!=='record',key==='cascade') }}><Button disabled={busy} icon={<MoreHorizontal size={15}/>}>删除与清理</Button></Dropdown></Space>}>
      {selected && <div className="model-detail-shell"><div className="detail-status"><TaskTag task={selected.task} /><StatusTag status={selected.status} /><strong>{selected.primaryMetricLabel} {selected.primaryMetric.toFixed(3)}</strong>{['published','archived'].includes(selected.status) && <Button size="small" loading={busy} icon={<Download size={14}/>} onClick={()=>void exportModel()}>导出发布包</Button>}</div>
        <Descriptions size="small" column={1} bordered items={[{key:'dataset',label:'数据集版本',children:selected.datasetName},{key:'run',label:'训练运行',children:selected.trainingRunId},{key:'env',label:'运行环境',children:selected.environment},...artifactRows]} />
        <ModelGateDiagnosticsPanel model={selected} report={gateReport} loading={gateReportLoading} />
        <ModelGateHistoryPanel runs={gateRuns} loading={gateRunsLoading} mobile={true} modelStatus={selected.status} busy={busy} onDelete={deleteGateRun} />
      </div>}
    </Drawer>
  </div>
}
