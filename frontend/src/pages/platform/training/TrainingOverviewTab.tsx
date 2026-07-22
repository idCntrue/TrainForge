import { Alert, Progress, Tag, Tooltip } from 'antd'
import { CircleHelp, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import type { TrainingRun } from '../../../platform/types'
import { phaseLabel } from '../../../components/platform/statusPresentation'
import { earlyStopSummary, metricText, timingText } from './trainingDetails'
import { lossCards, metricCards, splitPresentation } from './trainingDashboardPresentation'
import { TrainingEvidencePanel } from './TrainingEvidencePanel'
import { TrainingFailurePanel } from './TrainingFailurePanel'
import { TrainingQualitySummary } from './TrainingQualitySummary'

const trendPresentation = {
  improving: { label: '最近 5 轮整体下降', className: 'improving', icon: <TrendingDown size={14} /> },
  stable: { label: '最近 5 轮变化较小', className: 'stable', icon: <Minus size={14} /> },
  worsening: { label: '最近 5 轮整体上升', className: 'worsening', icon: <TrendingUp size={14} /> },
  unavailable: { label: '积累至少 2 轮后判断', className: 'unavailable', icon: <Minus size={14} /> },
} as const

const splitPurpose = {
  train: '用于更新模型参数',
  val: '用于逐轮评估与选择最佳权重',
  test: '训练结束后用于独立复核',
} as const

function ConfigItem({ label, children, title }: { label: string; children: React.ReactNode; title?: string }) {
  return <div title={title}><dt>{label}</dt><dd>{children}</dd></div>
}

function statusColor(status: TrainingRun['status']) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'cancelled' || status === 'interrupted') return 'default'
  return 'processing'
}

export function TrainingOverviewTab({ run, details, recoveryPending = false, onSafeRetry = () => {}, onEvaluateBest = () => {} }: {
  run: TrainingRun
  details: TrainingRunDetailsApiResponse
  recoveryPending?: boolean
  onSafeRetry?: () => void
  onEvaluateBest?: () => void
}) {
  const split = splitPresentation(details.split_distribution.split_counts)
  const quality = metricCards(details.configuration.task_type, details.epoch_history)
  const losses = lossCards(details.configuration.task_type, details.epoch_history)
  const active = ['queued', 'running', 'evaluating', 'exporting', 'verifying'].includes(run.status)
  const classes = details.configuration.selected_classes
  const mosaic = details.configuration.close_mosaic

  return <div className="training-detail-stack">
    {run.status === 'failed' && details.failure_diagnostic && <TrainingFailurePanel
      diagnostic={details.failure_diagnostic}
      recovery={details.recovery_options}
      latestMetric={run.metrics.primary}
      logs={details.logs}
      pending={recoveryPending}
      onSafeRetry={onSafeRetry}
      onEvaluateBest={onEvaluateBest}
    />}
    {run.status === 'completed' && details.quality_report && <TrainingQualitySummary report={details.quality_report} metrics={details.test_metrics} />}
    {run.status === 'completed' && <Alert type={details.completion?.stopped_early ? 'success' : 'info'} showIcon message={details.completion?.stopped_early ? '训练已正常提前停止' : '训练已完成'} description={earlyStopSummary(details.completion, details.configuration.patience)} />}
    {details.dataset_quality && <TrainingEvidencePanel report={details.dataset_quality} />}

    <section className="training-run-strip" aria-label="训练运行状态">
      <div className="training-run-heading">
        <div><span>当前阶段</span><Tag color={statusColor(run.status)}>{phaseLabel(run.phase)}</Tag></div>
        <strong>{active ? '模型正在学习数据特征' : run.status === 'completed' ? '本次训练已经结束' : '本次运行已停止'}</strong>
        <Progress percent={Math.round(run.progress)} status={run.status === 'failed' ? 'exception' : run.status === 'completed' ? 'success' : 'active'} showInfo={false} />
      </div>
      <div className="training-run-stat-grid">
        <div><span>训练轮次</span><strong>{run.epoch} / {run.epochs}</strong></div>
        <div><span>完成进度</span><strong>{Math.round(run.progress)}%</strong></div>
        <div><span>已运行</span><strong>{run.duration || '计算中'}</strong></div>
        <div><span>单轮平均</span><strong>{timingText(run.status, details.timing.epoch_seconds, 'epoch')}</strong></div>
        <div><span>预计剩余</span><strong>{timingText(run.status, details.timing.eta_seconds, 'eta')}</strong></div>
      </div>
    </section>

    <section className="training-summary-section" aria-labelledby="training-quality-heading">
      <div className="training-section-heading"><div><h3 id="training-quality-heading">核心质量指标</h3><p>来自最近一次有效验证；同一数据集内通常越高越好。</p></div><Tag>{details.epoch_history.length ? `最新第 ${details.epoch_history.at(-1)?.epoch} 轮` : '尚无验证结果'}</Tag></div>
      <div className="training-summary-grid training-quality-grid">
        {quality.map((item) => <article className="training-summary-metric" key={item.key}>
          <div><span>{item.label}</span><Tooltip title={item.help}><CircleHelp size={14} /></Tooltip></div>
          <strong>{item.value == null ? '--' : metricText(item.value)}</strong>
          <small>{item.value == null ? '首轮验证完成后生成' : item.help}</small>
        </article>)}
      </div>
    </section>

    <section className="training-summary-section" aria-labelledby="training-loss-heading">
      <div className="training-section-heading"><div><h3 id="training-loss-heading">训练 Loss 分解</h3><p>关注连续多轮趋势；不同任务的 Loss 绝对值不能直接比较。</p></div></div>
      {losses.length ? <div className="training-summary-grid training-loss-grid">
        {losses.map((item) => {
          const trend = trendPresentation[item.trend.state]
          return <article className="training-summary-metric" key={item.key}>
            <div><span>{item.label}</span><Tooltip title={item.help}><CircleHelp size={14} /></Tooltip></div>
            <strong>{metricText(item.value)}</strong>
            <small className={`training-loss-trend ${trend.className}`}>{trend.icon}{trend.label}</small>
          </article>
        })}
      </div> : <Alert type="info" showIcon message="首轮训练完成后生成 Loss 分解" />}
    </section>

    <section className="training-dataset-summary" aria-labelledby="training-dataset-heading">
      <div className="training-section-heading"><div><h3 id="training-dataset-heading">训练、验证与测试数据</h3><p>共 {split.total} 张图片，三部分职责不同，避免使用同一批数据自我评估。</p></div></div>
      <div className="training-split-bar" aria-label={`数据集共 ${split.total} 张`}>
        {split.items.map((item) => <span key={item.key} className={`training-split-${item.key}`} style={{ width: `${item.percent}%` }} />)}
      </div>
      <div className="training-split-legend training-split-explained">
        {split.items.map((item) => <div key={item.key}><i className={`training-split-${item.key}`} /><span>{item.label}</span><strong>{item.count} 张 · {item.percent}%</strong><small>{splitPurpose[item.key]}</small></div>)}
      </div>
      {!split.total && <Alert type="info" showIcon message="当前运行没有可用的数据划分统计" />}
    </section>

    <section className="training-config-section" aria-labelledby="training-config-heading">
      <div className="training-section-heading"><div><h3 id="training-config-heading">关键训练配置</h3><p>用于复核本次运行采用的模型、资源与训练策略。</p></div></div>
      <dl className="training-config-summary">
        <ConfigItem label="基础模型" title={details.configuration.base_model}>{details.configuration.base_model}</ConfigItem>
        <ConfigItem label="任务类型">{details.configuration.task_type === 'segment' ? '实例分割' : '目标检测'}</ConfigItem>
        <ConfigItem label="训练设备">{details.configuration.device}</ConfigItem>
        <ConfigItem label="Batch">{details.configuration.batch}</ConfigItem>
        <ConfigItem label="输入尺寸">{details.configuration.image_size} px</ConfigItem>
        <ConfigItem label="优化器">{details.configuration.optimizer ?? '历史版本未记录'}</ConfigItem>
        <ConfigItem label="数据增强">{details.configuration.augment_profile ?? '历史版本未记录'}</ConfigItem>
        <ConfigItem label="提前停止">{details.configuration.patience === 0 ? '已关闭，将尝试跑满轮次' : details.configuration.patience != null ? `连续 ${details.configuration.patience} 轮未改善后停止` : '历史版本未记录'}</ConfigItem>
        <ConfigItem label="Mosaic 收尾策略">{mosaic == null ? '历史版本未记录' : mosaic > 0 ? `最后 ${mosaic} 轮停止 Mosaic` : '全程不主动关闭 Mosaic'}</ConfigItem>
        <ConfigItem label="数据集版本" title={details.configuration.dataset_release_id}>{details.configuration.dataset_release_id}</ConfigItem>
      </dl>
      <div className="training-class-row"><span>训练类别</span><div className="training-class-tags">{classes.length ? classes.map((name) => <Tag key={name}>{name}</Tag>) : <Tag>全部类别</Tag>}</div></div>
    </section>

    {details.warnings.map((warning) => <Alert key={warning} type="info" showIcon message={warning} />)}
  </div>
}
