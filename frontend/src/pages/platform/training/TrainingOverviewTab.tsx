import { Alert, Card, Descriptions, Progress, Tag, Tooltip } from 'antd'
import { CircleHelp, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import type { TrainingRun } from '../../../platform/types'
import { earlyStopSummary, epochProgressText, metricText, timingText } from './trainingDetails'
import { lossTrend, splitPresentation } from './trainingDashboardPresentation'
import { TrainingFailurePanel } from './TrainingFailurePanel'
import { TrainingQualitySummary } from './TrainingQualitySummary'
import { TrainingEvidencePanel } from './TrainingEvidencePanel'
import { phaseLabel } from '../../../components/platform/statusPresentation'

const trendPresentation = {
  improving: { label: '训练损耗近期下降', color: 'success', icon: <TrendingDown size={14} /> },
  stable: { label: '近期变化较小', color: 'default', icon: <Minus size={14} /> },
  worsening: { label: '近期上升，建议观察验证指标', color: 'warning', icon: <TrendingUp size={14} /> },
  unavailable: { label: '积累更多轮次后判断', color: 'default', icon: <Minus size={14} /> },
} as const

export function TrainingOverviewTab({ run, details, recoveryPending = false, onSafeRetry = () => {}, onEvaluateBest = () => {} }: {
  run: TrainingRun
  details: TrainingRunDetailsApiResponse
  recoveryPending?: boolean
  onSafeRetry?: () => void
  onEvaluateBest?: () => void
}) {
  const split = splitPresentation(details.split_distribution.split_counts)
  const lossKey = details.configuration.task_type === 'segment' ? 'train_seg_loss' : 'train_box_loss'
  const trend = lossTrend(details.epoch_history, lossKey)
  const trendUi = trendPresentation[trend.state]
  const active = ['queued', 'running', 'evaluating', 'exporting', 'verifying'].includes(run.status)

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

    <Card className="training-progress-card" size="small">
      <div className="training-progress-layout">
        <Progress
          type="circle"
          percent={Math.round(run.progress)}
          size={132}
          status={run.status === 'failed' ? 'exception' : run.status === 'completed' ? 'success' : 'active'}
          format={() => <span className="training-epoch-value"><strong>{run.epoch}</strong><small>/ {run.epochs} 轮</small></span>}
        />
        <div className="training-progress-copy">
          <Tag color={active ? 'processing' : run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'default'}>{phaseLabel(run.phase)}</Tag>
          <h3>{active ? '模型正在学习数据特征' : run.status === 'completed' ? '本次训练已经结束' : '本次运行已停止'}</h3>
          <p>当前进度 {epochProgressText(run.status, run.epoch, run.epochs)}。预计剩余 {timingText(run.status, details.timing.eta_seconds, 'eta')}，单轮平均 {timingText(run.status, details.timing.epoch_seconds, 'epoch')}。</p>
        </div>
      </div>
    </Card>

    <div className="training-kpi-grid">
      <Card size="small" title={<span className="training-card-title">{run.metrics.primaryLabel}<Tooltip title="这是当前任务的主要验证指标，数值越高通常越好，但发布前仍需结合独立测试集和运行门禁。"><CircleHelp size={14} /></Tooltip></span>}>
        <strong className="training-kpi-value">{metricText(run.metrics.primary)}</strong>
        <p>{run.metrics.primary == null ? '尚未产生验证结果，完成有效评估轮次后自动显示。' : '当前验证结果已同步，不等同于生产环境最终效果。'}</p>
      </Card>
      <Card size="small" title={<span className="training-card-title">训练损耗 Loss<Tooltip title="Loss 表示模型预测与标注答案之间的差距。应关注一段时间内的趋势，而不是比较不同任务之间的绝对数值。"><CircleHelp size={14} /></Tooltip></span>}>
        <strong className="training-kpi-value">{metricText(trend.latest)}</strong>
        <Tag color={trendUi.color} icon={trendUi.icon}>{trendUi.label}</Tag>
      </Card>
    </div>

    <Card size="small" title="训练、验证与测试数据">
      <div className="training-split-bar" aria-label={`数据集共 ${split.total} 张`}>
        {split.items.map((item) => <span key={item.key} className={`training-split-${item.key}`} style={{ width: `${item.percent}%` }} />)}
      </div>
      <div className="training-split-legend">
        {split.items.map((item) => <div key={item.key}><i className={`training-split-${item.key}`} /><span>{item.label}</span><strong>{item.count} 张</strong><small>{item.percent}%</small></div>)}
      </div>
      {!split.total && <Alert type="info" showIcon message="当前运行没有可用的数据划分统计" />}
    </Card>

    <Descriptions size="small" bordered column={{ xs: 1, sm: 2, md: 3 }} items={[
      { key: 'device', label: '训练设备', children: details.configuration.device },
      { key: 'model', label: '基础模型', children: details.configuration.base_model },
      { key: 'batch', label: '批大小 Batch', children: details.configuration.batch },
      { key: 'size', label: '输入尺寸', children: `${details.configuration.image_size} px` },
      { key: 'dataset', label: '数据集版本', children: details.configuration.dataset_release_id },
      { key: 'classes', label: '训练类别', children: details.configuration.selected_classes.join('、') || '全部类别' },
      { key: 'patience', label: '提前停止', children: details.configuration.patience === 0 ? '已关闭' : details.configuration.patience != null ? `${details.configuration.patience} 轮` : '历史版本未记录' },
    ]} />
    {details.warnings.map((warning) => <Alert key={warning} type="info" showIcon message={warning} />)}
  </div>
}
