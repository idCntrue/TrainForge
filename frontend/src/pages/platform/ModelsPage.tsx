import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Descriptions, Drawer, Dropdown, message, Modal, Select, Space, Table, Tooltip } from 'antd'
import { Archive, Box, CheckCircle2, Copy, FileCode2, MoreHorizontal, Play, Send, ShieldCheck } from 'lucide-react'

import { api } from '../../api'
import type { ModelGateReportApiResponse } from '../../api'
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

export default function ModelsPage() {
  const isMobile = useMobileViewport()
  const [models, setModels] = useState<ModelArtifact[]>([]), [selected, setSelected] = useState<ModelArtifact>(), [busy, setBusy] = useState(false)
  const [gateReport, setGateReport] = useState<ModelGateReportApiResponse>(), [gateReportLoading, setGateReportLoading] = useState(false)
  const operationGate = useRef(createOperationGate())
  const [task, setTask] = useState<TaskType>(), [status, setStatus] = useState<ModelStatus>()
  const load = useCallback(async () => { const next = await platformRepository.listModels({ task, status }); setModels(next); setSelected((current)=>current ? next.find((item)=>item.id===current.id) ?? current : undefined) }, [task, status])
  useEffect(() => { void load().catch((error)=>message.error(error.message)) }, [load])
  useEffect(() => {
    if (!selected) { setGateReport(undefined); return }
    let active = true
    setGateReport(undefined)
    setGateReportLoading(true)
    void api.getModelGateReport(selected.id)
      .then((report) => { if (active) setGateReport(report) })
      .catch(() => { if (active) message.warning('门禁诊断详情读取失败，可重新运行门禁后再试。') })
      .finally(() => { if (active) setGateReportLoading(false) })
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
          setGateReport(await api.getModelGateReport(mapped.id))
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
  const published = models.filter((model) => model.status === 'published').length
  const artifactRows = selected ? Object.entries(selected.artifacts).map(([format, artifact]) => ({
    key: `artifact-${format}`,
    label: `${format.toUpperCase()} 制品`,
    children: <div style={{ display: 'grid', gap: 6 }}><span>{artifact.exists ? `${(artifact.sizeBytes / 1024 / 1024).toFixed(1)} MB` : '文件不存在'}</span><Space.Compact style={{ width: '100%' }}><Tooltip title={artifact.path}><code style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: '5px 8px', border: '1px solid #d9d9d9' }}>{artifact.path}</code></Tooltip><Button icon={<Copy size={14} />} title="复制实际路径" onClick={() => void navigator.clipboard.writeText(artifact.path).then(() => message.success('路径已复制'))} /></Space.Compact><small>SHA-256：{artifact.sha256 || '-'}</small></div>,
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
    <Drawer className="mobile-fullscreen-drawer" width={isMobile ? '100%' : 680} title={selected ? `${selected.name} v${selected.version}` : ''} open={Boolean(selected)} onClose={() => setSelected(undefined)} extra={selected && <Space>{['candidate','blocked'].includes(selected.status) && <Button loading={busy} disabled={busy} icon={<Play size={15}/>} onClick={()=>void action('gates')}>运行门禁</Button>}{selected.status === 'candidate' && selected.gates.every((gate)=>gate.advisory || gate.status==='passed') && <Button loading={busy} disabled={busy} type="primary" icon={<Send size={15}/>} onClick={()=>void action('publish')}>发布</Button>}{selected.status === 'published' && <Button loading={busy} disabled={busy} icon={<Archive size={15}/>} onClick={()=>void action('archive')}>归档</Button>}<Dropdown trigger={['click']} menu={{ items: [...(selected.status !== 'published' ? [{ key:'record',label:'仅删除模型记录' },{ key:'artifacts',label:'删除记录并清理制品',danger:true }] : []),{ key:'cascade',label:'级联删除模型与推理历史',danger:true }], onClick:({key})=>deleteModel(key!=='record',key==='cascade') }}><Button disabled={busy} icon={<MoreHorizontal size={15}/>}>删除与清理</Button></Dropdown></Space>}>
      {selected && <div className="platform-stack compact"><div className="detail-status"><TaskTag task={selected.task} /><StatusTag status={selected.status} /><strong>{selected.primaryMetricLabel} {selected.primaryMetric.toFixed(3)}</strong></div>
        <Descriptions size="small" column={1} bordered items={[{key:'dataset',label:'数据集版本',children:selected.datasetName},{key:'run',label:'训练运行',children:selected.trainingRunId},{key:'env',label:'运行环境',children:selected.environment},...artifactRows]} />
        <ModelGateDiagnosticsPanel model={selected} report={gateReport} loading={gateReportLoading} />
      </div>}
    </Drawer>
  </div>
}
