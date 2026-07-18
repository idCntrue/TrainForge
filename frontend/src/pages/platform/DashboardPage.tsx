import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Progress, Skeleton, Tag } from 'antd'
import {
  ArrowRight, Box, Check, CircleDashed, Clock3, Cpu, Database,
  FlaskConical, Gauge, Rocket, ScanSearch, ShieldCheck, Sparkles,
} from 'lucide-react'

import { StatusTag } from '../../components/platform/StatusTag'
import { TaskTag } from '../../components/platform/TaskTag'
import type { ViewKey } from '../../navigation'
import { platformRepository } from '../../platform/repository'
import type { DashboardData, TrainingRun } from '../../platform/types'
import { recommendNextAction } from '../../platform/workflow'
import { releaseFunnel, workflowStages } from './dashboardPresentation'

const metricText = (run: TrainingRun) => run.metrics.primary == null ? '待生成' : run.metrics.primary.toFixed(3)

export default function DashboardPage({ onNavigate }: { onNavigate: (view: ViewKey) => void }) {
  const [data, setData] = useState<DashboardData>()
  const [error, setError] = useState('')
  const load = () => {
    setError('')
    void platformRepository.getDashboard().then(setData).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : '无法加载工作台数据')
    })
  }
  useEffect(load, [])
  const action = useMemo(() => data ? recommendNextAction(data.totals) : undefined, [data])
  if (error) return <Alert type="error" showIcon message="工作台数据加载失败" description={error} action={<Button onClick={load}>重新加载</Button>} />
  if (!data || !action) return <Skeleton active paragraph={{ rows: 10 }} />

  const stages = workflowStages(data.totals)
  const funnel = releaseFunnel(data.totals.models, data.totals.publishedModels)
  const metrics = [
    { label: '数据集版本', value: data.totals.datasetReleases, detail: data.totals.datasetReleases ? '可用于训练的数据资产' : '等待发布首个版本', icon: Database, tone: 'teal', view: 'datasets' as ViewKey },
    { label: '训练运行', value: data.totals.trainingRuns, detail: data.activeRun ? '当前有任务运行中' : '当前无进行中的训练运行', icon: FlaskConical, tone: 'blue', view: 'training' as ViewKey },
    { label: '模型资产', value: data.totals.models, detail: `${data.totals.publishedModels} 个已经发布`, icon: Box, tone: 'green', view: 'models' as ViewKey },
    { label: '推理验证', value: data.totals.inferenceRuns, detail: data.totals.inferenceRuns ? '已有真实验证记录' : '尚未执行推理', icon: ScanSearch, tone: 'amber', view: 'inference' as ViewKey },
  ]

  return <div className="platform-stack command-dashboard">
    <section className="command-hero">
      <div className="command-hero-main">
        <div className="command-live"><span /><strong>YOLO Factory Control</strong><small>实时业务总览</small></div>
        <span className="command-eyebrow"><Sparkles size={14} />{action.stage} · 推荐下一步</span>
        <h2>{action.title}</h2>
        <p>{action.description}</p>
        <div className="command-hero-actions">
          <Button type="primary" icon={<ArrowRight size={16} />} onClick={() => onNavigate(action.view)}>{action.buttonLabel}</Button>
          <Button ghost onClick={() => onNavigate('help')}>打开用户手册</Button>
        </div>
      </div>
      <div className="command-stage-rail">
        {stages.map((stage, index) => <div className={`command-stage ${stage.state}`} key={stage.key}>
          <span>{stage.state === 'done' ? <Check size={15} /> : stage.state === 'current' ? <CircleDashed size={15} /> : index + 1}</span>
          <div><small>0{index + 1}</small><strong>{stage.label}</strong><p>{stage.detail}</p></div>
        </div>)}
      </div>
    </section>

    <section className="command-metrics">
      {metrics.map(({ icon: Icon, ...item }) => <button key={item.label} type="button" className={`command-metric ${item.tone}`} onClick={() => onNavigate(item.view)}>
        <span className="command-metric-icon"><Icon size={19} /></span>
        <div><small>{item.label}</small><strong>{item.value}</strong><p>{item.detail}</p></div>
        <ArrowRight className="command-metric-arrow" size={15} />
      </button>)}
    </section>

    <section className="command-core-grid">
      <div className="command-training-panel">
        <div className="command-panel-heading"><div><span className="command-section-kicker"><Gauge size={14} />实时计算</span><h3>当前训练</h3></div>{data.activeRun && <TaskTag task={data.activeRun.task} />}</div>
        {data.activeRun ? <div className="command-active-run">
          <div className="command-run-title"><div><strong>{data.activeRun.name}</strong><span>{data.activeRun.datasetName}</span></div><StatusTag status={data.activeRun.status} /></div>
          <div className="command-run-progress"><Progress type="circle" percent={Math.round(data.activeRun.progress)} size={116} strokeWidth={9} /><div className="command-run-facts">
            <div><span><FlaskConical size={14} />训练轮次</span><strong>{data.activeRun.epoch} / {data.activeRun.epochs}</strong></div>
            <div><span><Cpu size={14} />计算设备</span><strong>{data.activeRun.device}</strong></div>
            <div><span><Clock3 size={14} />已运行</span><strong>{data.activeRun.duration}</strong></div>
            <div><span><Gauge size={14} />{data.activeRun.metrics.primaryLabel}</span><strong>{metricText(data.activeRun)}</strong></div>
          </div></div>
          <Button type="link" onClick={() => onNavigate('training')}>查看实时训练详情 <ArrowRight size={14} /></Button>
        </div> : <div className="command-idle-state"><div className="command-idle-pulse"><Cpu size={25} /></div><div><strong>当前无进行中的训练运行</strong><p>创建训练后，这里会实时显示轮次、设备、进度和主要指标。</p></div><Button type="primary" onClick={() => onNavigate('training')}>新建训练</Button></div>}
      </div>

      <div className="command-release-panel">
        <div className="command-panel-heading"><div><span className="command-section-kicker"><ShieldCheck size={14} />资产就绪度</span><h3>模型发布漏斗</h3></div><Tag color={funnel.published ? 'green' : 'default'}>{funnel.rate}% 已就绪</Tag></div>
        <div className="command-release-score"><strong>{funnel.published}</strong><span>/ {funnel.total} 个模型可用于推理</span></div>
        <Progress percent={funnel.rate} showInfo={false} strokeColor="#2f9b72" trailColor="#e5ebe8" />
        <div className="command-funnel-steps">
          <div><span><Box size={15} />模型资产</span><strong>{funnel.total}</strong></div>
          <ArrowRight size={16} />
          <div><span><ShieldCheck size={15} />待门禁或发布</span><strong>{funnel.pending}</strong></div>
          <ArrowRight size={16} />
          <div className="ready"><span><Rocket size={15} />可推理</span><strong>{funnel.published}</strong></div>
        </div>
        <p>只有完成质量评估并通过运行门禁的模型，才应进入推理验证。</p>
        <Button onClick={() => onNavigate('models')}>进入模型中心 <ArrowRight size={14} /></Button>
      </div>
    </section>

    <section className="command-recent-panel">
      <div className="command-panel-heading"><div><span className="command-section-kicker"><Clock3 size={14} />运行历史</span><h3>最近训练</h3></div><Button type="text" onClick={() => onNavigate('training')}>查看全部 <ArrowRight size={15} /></Button></div>
      {data.recentRuns.length ? <div className="command-run-list">{data.recentRuns.map((run) => <button type="button" key={run.id} onClick={() => onNavigate('training')}>
        <div className="command-run-index">{String(data.recentRuns.indexOf(run) + 1).padStart(2, '0')}</div>
        <div className="command-run-name"><strong>{run.name}</strong><span>{run.datasetName}</span></div>
        <TaskTag task={run.task} />
        <StatusTag status={run.status} />
        <div className="command-list-progress"><span>Epoch {run.epoch}/{run.epochs}</span><Progress percent={run.progress} size="small" showInfo={false} /></div>
        <div className="command-list-metric"><span>{run.metrics.primaryLabel}</span><strong>{metricText(run)}</strong></div>
        <ArrowRight size={16} />
      </button>)}</div> : <div className="command-empty-history"><FlaskConical size={22} /><div><strong>暂无真实训练记录</strong><span>先发布数据集，再创建第一条训练运行。</span></div><Button onClick={() => onNavigate('training')}>开始训练</Button></div>}
    </section>
  </div>
}
