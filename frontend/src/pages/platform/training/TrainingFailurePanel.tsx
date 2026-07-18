import { Alert, Button, Collapse, Descriptions, Space, Typography } from 'antd'
import { RefreshCw, ScanSearch } from 'lucide-react'
import type { TrainingFailureDiagnostic, TrainingRecoveryOptions } from '../../../api'
import { failedRunPresentation } from './trainingFailurePresentation'

export function TrainingFailurePanel({
  diagnostic, recovery, latestMetric, logs, pending, onSafeRetry, onEvaluateBest,
}: {
  diagnostic: TrainingFailureDiagnostic
  recovery: TrainingRecoveryOptions | null
  latestMetric?: number | null
  logs: string[]
  pending: boolean
  onSafeRetry: () => void
  onEvaluateBest: () => void
}) {
  const view = failedRunPresentation({
    lastSuccessfulEpoch: diagnostic.last_successful_epoch,
    totalEpochs: diagnostic.total_epochs,
    latestMetric,
    canSafeRetry: Boolean(recovery?.can_safe_retry),
    canEvaluateBest: Boolean(recovery?.can_evaluate_best),
  })
  return <section className="training-failure-panel" aria-label="训练失败诊断">
    <Alert
      type="error"
      showIcon
      message={diagnostic.summary}
      description={<div className="training-failure-summary">
        <strong>{view.progressText}</strong>
        <span>{diagnostic.action}</span>
        <span>截至失败前的指标：{view.metricText}</span>
      </div>}
    />
    <Descriptions size="small" column={3} items={[
      { key: 'phase', label: '失败阶段', children: diagnostic.failure_phase },
      { key: 'time', label: '发生时间', children: diagnostic.occurred_at },
      { key: 'artifacts', label: '保留产物', children: `${recovery?.preserved_artifact_count ?? 0} 项` },
    ]} />
    <Space wrap>
      {recovery?.can_safe_retry && <Button type="primary" loading={pending} icon={<RefreshCw size={15} />} onClick={onSafeRetry}>使用安全配置重试</Button>}
      {recovery?.can_evaluate_best && <Button loading={pending} icon={<ScanSearch size={15} />} onClick={onEvaluateBest}>评估已有最佳权重</Button>}
    </Space>
    {recovery && !recovery.can_safe_retry && !recovery.can_evaluate_best && <Typography.Text type="secondary">{recovery.reason}</Typography.Text>}
    <Collapse ghost items={[{
      key: 'technical', label: '技术诊断', children: <div className="training-technical-diagnostic">
        <Typography.Paragraph copyable>{diagnostic.code} / exit {diagnostic.exit_code ?? '--'}</Typography.Paragraph>
        <pre>{diagnostic.traceback || diagnostic.technical_message || logs.slice(-200).join('\n') || '暂无更多日志'}</pre>
      </div>,
    }]} />
  </section>
}
