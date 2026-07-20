import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ModelGateReportApiResponse } from '../../api'
import type { ModelArtifact } from '../../platform/types'
import { ModelGateDiagnosticsPanel } from './ModelGateDiagnosticsPanel'

const model: ModelArtifact = {
  id: 'model-1', name: '乘梯标识', version: '1.0.0', task: 'segment', status: 'blocked', datasetReleaseId: 'dataset-1', datasetName: 'dataset-1',
  trainingRunId: 'training-1', primaryMetric: 0.971, primaryMetricLabel: 'Mask mAP50', sizeMb: 10, formats: ['PT', 'ONNX'], createdAt: '2026-07-20',
  baseModel: '-', weightHash: 'hash', environment: '-', gateReportPath: 'report.json',
  gates: [
    { key: 'training', label: '训练已完成', status: 'passed', detail: '', advisory: false },
    { key: 'consistency', label: 'PT 与 ONNX 推理一致性', status: 'blocked', detail: '', advisory: false },
    { key: 'quality_recommended', label: '推荐发布质量', status: 'blocked', detail: '', advisory: true },
  ],
}

const report: ModelGateReportApiResponse = {
  available: true,
  reason: null,
  report: {
    passed: false,
    samples: [{
      source: 'D:\\YOLO_DATA\\dataset-releases\\problem.jpg', passed: false, pt_count: 2, onnx_count: 1,
      pairs: [{ class_id: 0, box_iou: 0.68, confidence_delta: 0.14, mask_iou: 0.49, passed: false }],
    }],
  },
}

describe('ModelGateDiagnosticsPanel', () => {
  it('renders a Chinese summary, advisory meaning and expanded failed evidence', () => {
    const html = renderToStaticMarkup(<ModelGateDiagnosticsPanel model={model} report={report} loading={false} />)

    expect(html).toContain('1 项通过，1 项阻止发布，1 项质量建议未达标')
    expect(html).toContain('PT 与 ONNX 推理一致性')
    expect(html).toContain('建议项，不单独阻止发布')
    expect(html).toContain('problem.jpg')
    expect(html).toContain('PT 2 个，ONNX 1 个')
    expect(html).toContain('Mask IoU 0.490')
    expect(html).not.toContain('YOLO_DATA')
  })

  it('tells users to rerun gates when historical evidence is missing', () => {
    const html = renderToStaticMarkup(<ModelGateDiagnosticsPanel
      model={model}
      report={{ available: false, report: null, reason: 'missing' }}
      loading={false}
    />)
    expect(html).toContain('暂无诊断详情，请重新运行门禁')
  })
})
