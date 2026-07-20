import { describe, expect, it } from 'vitest'

import type { ModelGateReportApiResponse, TrainingQualityReport } from '../../api'
import type { ModelArtifact } from '../../platform/types'
import {
  buildGateDiagnostics,
  gateCompletionFeedback,
  gateDefinition,
  qualityRecommendation,
  summarizeConsistency,
} from './modelGateDiagnostics'

const failedReport: ModelGateReportApiResponse = {
  available: true,
  reason: null,
  report: {
    passed: false,
    gates: { training: true, pt: true, onnx: true, consistency: false },
    samples: [
      {
        source: 'D:\\YOLO_DATA\\dataset-releases\\sample-a.jpg',
        passed: false,
        pt_count: 2,
        onnx_count: 1,
        pairs: [{ class_id: 0, box_iou: 0.68, confidence_delta: 0.14, mask_iou: 0.49, passed: false }],
      },
      {
        source: '/data/dataset-releases/sample-b.jpg',
        passed: false,
        pt_count: 2,
        onnx_count: 2,
        pairs: [{ class_id: 0, box_iou: 0.99, confidence_delta: 0.01, mask_iou: 0, passed: false }],
      },
    ],
  },
}

const qualityReport: TrainingQualityReport = {
  verdict: 'insufficient_evidence', confidence: 'low', reasons: ['garbled'], recommendations: ['garbled'], best_epoch: 25,
  weakest_classes: [],
  thresholds: {
    min_test_images: 30,
    min_test_instances_per_class: 10,
    ready: { precision: 0.8, recall: 0.8, map50_95: 0.5 },
  },
}

function model(gates: Record<string, boolean>): ModelArtifact {
  return {
    id: 'model-1', name: 'test', version: '1.0.0', task: 'segment', status: 'blocked', datasetReleaseId: 'dataset-1', datasetName: 'dataset-1',
    trainingRunId: 'training-1', primaryMetric: 0.9, primaryMetricLabel: 'Mask mAP50', sizeMb: 10, formats: ['PT', 'ONNX'], createdAt: '2026-07-20',
    baseModel: '-', weightHash: 'hash', environment: '-', gateReportPath: 'report.json', qualityReport,
    gates: Object.entries(gates).map(([key, passed]) => ({ key, label: key, status: passed ? 'passed' : 'blocked', detail: '', advisory: key === 'quality_recommended' })),
  }
}

describe('model gate diagnostics', () => {
  it('uses Chinese labels and distinguishes advisory checks', () => {
    expect(gateDefinition('consistency')).toMatchObject({ label: 'PT 与 ONNX 推理一致性', advisory: false })
    expect(gateDefinition('quality_recommended')).toMatchObject({ label: '推荐发布质量', advisory: true })
    expect(gateDefinition('unknown').label).toBe('unknown')
  })

  it('summarizes count, box and mask differences without exposing absolute paths', () => {
    const result = summarizeConsistency(failedReport.report!)

    expect(result.summary).toContain('2 张验证图片未通过')
    expect(result.summary).toContain('1 张目标数量不一致')
    expect(result.summary).toContain('1 张存在检测框差异')
    expect(result.summary).toContain('2 张存在分割轮廓差异')
    expect(result.samples.map((sample) => sample.filename)).toEqual(['sample-a.jpg', 'sample-b.jpg'])
    expect(result.samples[0].issues).toEqual(expect.arrayContaining([
      '目标数量：PT 2 个，ONNX 1 个',
      '框 IoU 0.680，低于要求 0.800',
      'Mask IoU 0.490，低于要求 0.750',
    ]))
    expect(result.samples[1].issues).toContain('Mask IoU 0.000，低于要求 0.750')
    expect(JSON.stringify(result)).not.toContain('YOLO_DATA')
    expect(JSON.stringify(result)).not.toContain('/data/')
  })

  it('explains insufficient quality evidence from structured verdict and thresholds', () => {
    expect(qualityRecommendation(qualityReport)).toEqual({
      summary: '独立测试证据不足，当前指标还不能可靠代表真实效果。',
      recommendation: '建议至少准备 30 张独立测试图片，并保证每个类别至少有 10 个测试实例后重新评估。',
    })
  })

  it('builds an overview with hard failures separated from advisory failures', () => {
    const result = buildGateDiagnostics(
      model({ training: true, pt: true, onnx: true, consistency: false, independent_test_available: true, quality_recommended: false }),
      failedReport,
    )

    expect(result.summary).toBe('4 项通过，1 项阻止发布，1 项质量建议未达标。')
    expect(result.hardFailures).toBe(1)
    expect(result.advisoryFailures).toBe(1)
    expect(result.items.find((item) => item.key === 'consistency')?.detail).toContain('2 张验证图片未通过')
    expect(result.items.find((item) => item.key === 'quality_recommended')?.detail).toContain('不单独阻止发布')
  })

  it('returns a clear fallback when historical details are unavailable', () => {
    const result = buildGateDiagnostics(model({ consistency: false }), { available: false, report: null, reason: 'missing' })
    expect(result.reportUnavailable).toBe('暂无诊断详情，请重新运行门禁。')
  })

  it('selects accurate completion feedback', () => {
    expect(gateCompletionFeedback(model({ training: true, pt: true, onnx: true, consistency: true, independent_test_available: true, quality_recommended: true }))).toEqual({
      type: 'success', message: '门禁检查完成，可以发布。',
    })
    expect(gateCompletionFeedback(model({ training: true, pt: true, onnx: true, consistency: false, independent_test_available: true, quality_recommended: true }))).toEqual({
      type: 'warning', message: '门禁检查完成，发现 1 项阻止发布的问题。',
    })
    expect(gateCompletionFeedback(model({ training: true, pt: true, onnx: true, consistency: true, independent_test_available: true, quality_recommended: false }))).toEqual({
      type: 'warning', message: '硬门禁已通过，但模型质量尚未达到推荐线。',
    })
  })
})
