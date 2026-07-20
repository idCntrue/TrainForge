import { Alert, Collapse, Progress, Skeleton, Tag } from 'antd'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'

import type { ModelGateReportApiResponse } from '../../api'
import type { ModelArtifact } from '../../platform/types'
import { buildGateDiagnostics, qualityRecommendation } from './modelGateDiagnostics'

export function ModelGateDiagnosticsPanel({
  model,
  report,
  loading,
}: {
  model: ModelArtifact
  report?: ModelGateReportApiResponse
  loading: boolean
}) {
  if (loading) return <div className="model-gate-loading"><Skeleton active paragraph={{ rows: 4 }} /></div>

  const diagnostics = buildGateDiagnostics(model, report)
  const quality = qualityRecommendation(model.qualityReport)
  const passed = diagnostics.items.filter((item) => item.status === 'passed').length
  const percent = diagnostics.items.length ? Math.round(passed / diagnostics.items.length * 100) : 0

  return <section className="model-gate-diagnostics" aria-label="模型门禁诊断">
    <Alert
      type={diagnostics.hardFailures ? 'error' : diagnostics.advisoryFailures ? 'warning' : 'success'}
      showIcon
      message={diagnostics.hardFailures ? '存在阻止发布的问题' : diagnostics.advisoryFailures ? '硬门禁已通过，质量建议未达标' : '全部门禁已通过'}
      description={diagnostics.summary}
    />

    {diagnostics.reportUnavailable && <Alert type="info" showIcon message={diagnostics.reportUnavailable} />}

    <Collapse
      className="model-gate-collapse"
      defaultActiveKey={diagnostics.items.filter((item) => item.expanded).map((item) => item.key)}
      items={diagnostics.items.map((item) => ({
        key: item.key,
        label: <div className="model-gate-heading">
          {item.status === 'passed' ? <CheckCircle2 size={17} className="gate-icon-passed" /> : <AlertTriangle size={17} className="gate-icon-blocked" />}
          <div><strong>{item.label}</strong><span>{item.detail}</span></div>
          {item.advisory && <Tag color="gold">建议项，不单独阻止发布</Tag>}
        </div>,
        children: <div className="model-gate-detail">
          {item.key === 'consistency' && item.samples?.map((sample) => <article className="model-gate-sample" key={sample.filename}>
            <div className="model-gate-sample-heading"><strong>{sample.filename}</strong><span>PT {sample.ptCount} 个 / ONNX {sample.onnxCount} 个</span></div>
            <ul>{sample.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
            <p><Info size={14} />建议先确认是否为同类别相邻目标的配对问题；若配对正确，再检查 ONNX 导出和分割后处理兼容性。</p>
          </article>)}
          {item.key === 'quality_recommended' && <div className="model-gate-recommendation">
            <p>{quality.summary}</p>
            <strong>{quality.recommendation}</strong>
          </div>}
          {item.key !== 'consistency' && item.key !== 'quality_recommended' && <p>{item.detail}</p>}
        </div>,
      }))}
    />

    <div className="model-gate-progress"><Progress percent={percent} strokeColor={diagnostics.hardFailures ? '#c53b32' : '#126e5b'} /><span>建议项会计入完成度，但不会单独阻止模型发布。</span></div>
  </section>
}
