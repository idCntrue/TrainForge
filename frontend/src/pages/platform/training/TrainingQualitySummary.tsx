import { Alert, Statistic } from 'antd'
import type { TestMetricsReport, TrainingQualityReport } from '../../../api'
import { metricText } from './trainingDetails'
import { qualityPresentation } from './trainingQualityPresentation'
import { ClassMetricsTable } from './ClassMetricsTable'

export function TrainingQualitySummary({ report, metrics }: { report: TrainingQualityReport; metrics: TestMetricsReport | null }) {
  const view = qualityPresentation(report)
  const overall = metrics?.overall ?? {}
  return <section className="training-quality-summary">
    <Alert type={view.tone} showIcon message={view.title} description={<>
      <strong>{view.confidenceLabel}</strong>
      {report.reasons.map((reason) => <div key={reason}>{reason}</div>)}
      {report.recommendations.map((item) => <div key={item}>建议：{item}</div>)}
    </>} />
    <div className="training-stat-grid">
      <Statistic title="检测结果中有多少正确（Precision）" value={metricText(overall.precision)} />
      <Statistic title="真实目标中有多少被找到（Recall）" value={metricText(overall.recall)} />
      <Statistic title="宽松综合精度 mAP50" value={metricText(overall.map50)} />
      <Statistic title="严格综合精度 mAP50-95" value={metricText(overall.map50_95)} />
    </div>
    {metrics?.per_class.length ? <ClassMetricsTable rows={metrics.per_class} /> : null}
  </section>
}
