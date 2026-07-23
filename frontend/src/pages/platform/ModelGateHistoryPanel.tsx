import { Button, Empty, Modal, Skeleton, Table, Tag, Tooltip } from 'antd'
import { AlertTriangle, CheckCircle2, Clock3, Trash2 } from 'lucide-react'

import type { ModelGateRunApiResponse } from '../../api'
import type { ModelStatus } from '../../platform/types'

export function formatGateBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function gateRunDeletionCopy(run: ModelGateRunApiResponse, runs: ModelGateRunApiResponse[], modelStatus: ModelStatus) {
  if (run.active && modelStatus === 'published') return {
    disabled: true,
    title: '当前门禁正在被已发布模型使用',
    content: '为避免发布模型的 ONNX 引用失效，当前门禁不能直接删除。请先归档模型，或运行一套新的门禁后再删除。',
  }
  if (!run.active) return {
    disabled: false,
    title: '删除这条历史门禁及文件？',
    content: '将删除本次门禁生成的 ONNX、报告、日志和对比图片，不影响当前模型，也不会删除训练生成的 best.pt 或 best.onnx。',
  }
  const fallback = runs.find((candidate) => candidate.id !== run.id && candidate.status !== 'incomplete' && candidate.onnx)
  if (fallback) return {
    disabled: false,
    title: '删除当前门禁并切换到上一套？',
    content: `删除后将自动切换到上一套门禁 ${fallback.id} 及其 ONNX。训练生成的 best.pt 和 best.onnx 不会被删除。`,
  }
  return {
    disabled: false,
    title: '删除最后一套门禁及文件？',
    content: '删除后模型会恢复为“待运行门禁”，发布前需要重新运行门禁。训练生成的 best.pt 和 best.onnx 不会被删除。',
  }
}

function state(run: ModelGateRunApiResponse) {
  if (run.status === 'incomplete') return { color: 'default', label: '未完成', icon: <Clock3 size={14} /> }
  if (run.status === 'blocked') return { color: 'error', label: '硬门禁未通过', icon: <AlertTriangle size={14} /> }
  if (run.status === 'completed_with_warnings') return { color: 'warning', label: '掩膜差异提醒', icon: <AlertTriangle size={14} /> }
  return { color: 'success', label: '已通过', icon: <CheckCircle2 size={14} /> }
}

function DeleteAction({ run, runs, modelStatus, busy, onDelete }: {
  run: ModelGateRunApiResponse
  runs: ModelGateRunApiResponse[]
  modelStatus: ModelStatus
  busy: boolean
  onDelete: (run: ModelGateRunApiResponse) => void | Promise<void>
}) {
  const copy = gateRunDeletionCopy(run, runs, modelStatus)
  const button = <Button
    danger
    size="small"
    disabled={busy || copy.disabled}
    icon={<Trash2 size={14} />}
    onClick={() => Modal.confirm({
      title: copy.title,
      content: copy.content,
      okText: run.active ? '确认删除并更新模型' : '删除此轮及文件',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => onDelete(run),
    })}
  >删除此轮及文件</Button>
  return copy.disabled ? <Tooltip title={copy.content}>{button}</Tooltip> : button
}

function RunDetails({ run }: { run: ModelGateRunApiResponse }) {
  return <details className="gate-history-files">
    <summary>查看文件与实际路径</summary>
    <dl>
      <dt>ONNX</dt><dd>{run.onnx?.path ?? '本轮未生成 ONNX'}</dd>
      <dt>门禁报告</dt><dd>{run.report_path ?? '本轮未生成报告'}</dd>
    </dl>
  </details>
}

export function ModelGateHistoryPanel({ runs, loading, mobile, modelStatus, busy, onDelete }: {
  runs: ModelGateRunApiResponse[]
  loading: boolean
  mobile: boolean
  modelStatus: ModelStatus
  busy: boolean
  onDelete: (run: ModelGateRunApiResponse) => void | Promise<void>
}) {
  if (loading) return <section className="gate-history"><h3>门禁历史</h3><Skeleton active paragraph={{ rows: 3 }} /></section>
  return <section className="gate-history" aria-label="门禁历史">
    <header><div><h3>门禁历史</h3><p>每轮门禁使用独立 ONNX；删除只清理该轮文件，不会清理训练权重。</p></div><Tag>{runs.length} 轮</Tag></header>
    {!runs.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无独立门禁记录，运行一次门禁后会显示在这里。" /> : mobile
      ? <div className="gate-history-mobile">{runs.map((run) => {
        const presentation = state(run)
        return <article className="gate-history-card" key={run.id}>
          <div className="gate-history-card-heading"><div><strong>{run.id}</strong><span>{new Date(run.created_at).toLocaleString('zh-CN')}</span></div><div>{run.active && <Tag color="blue">当前版本</Tag>}<Tag color={presentation.color} icon={presentation.icon}>{presentation.label}</Tag></div></div>
          <div className="gate-history-metrics"><span><small>ONNX</small><strong>{run.onnx ? formatGateBytes(run.onnx.size_bytes) : '-'}</strong></span><span><small>本轮全部文件</small><strong>{formatGateBytes(run.total_size_bytes)}</strong></span></div>
          <RunDetails run={run} />
          <div className="gate-history-actions"><DeleteAction run={run} runs={runs} modelStatus={modelStatus} busy={busy} onDelete={onDelete} /></div>
        </article>
      })}</div>
      : <Table size="small" pagination={false} rowKey="id" dataSource={runs} expandable={{ expandedRowRender: (run) => <RunDetails run={run} /> }} columns={[
        { title: '运行时间', render: (_, run) => <div className="table-primary"><strong>{new Date(run.created_at).toLocaleString('zh-CN')}</strong><span>{run.id}</span></div> },
        { title: '版本', width: 90, render: (_, run) => run.active ? <Tag color="blue">当前版本</Tag> : <Tag>历史版本</Tag> },
        { title: '结果', width: 150, render: (_, run) => { const item = state(run); return <Tag color={item.color} icon={item.icon}>{item.label}</Tag> } },
        { title: 'ONNX', width: 90, render: (_, run) => run.onnx ? formatGateBytes(run.onnx.size_bytes) : '-' },
        { title: '占用', width: 90, render: (_, run) => formatGateBytes(run.total_size_bytes) },
        { title: '操作', width: 150, render: (_, run) => <DeleteAction run={run} runs={runs} modelStatus={modelStatus} busy={busy} onDelete={onDelete} /> },
      ]} />}
  </section>
}
