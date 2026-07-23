import type { ModelGateReport, ModelGateReportApiResponse, ModelGateSampleReport, TrainingQualityReport } from '../../api'
import type { ModelArtifact, ReleaseGate } from '../../platform/types'

const BOX_IOU_MIN = 0.8
const CONFIDENCE_DELTA_MAX = 0.15
const MASK_IOU_MIN = 0.75

const definitions: Record<string, { label: string; description: string; advisory: boolean }> = {
  training: { label: '训练已完成', description: '训练流程已正常完成并生成模型产物。', advisory: false },
  pt: { label: 'PT 模型文件', description: '原始 PyTorch 模型文件存在且可以读取。', advisory: false },
  onnx: { label: 'ONNX 模型文件', description: '已成功导出可部署的 ONNX 模型文件。', advisory: false },
  consistency: { label: 'PT 与 ONNX 推理一致性', description: '验证 PT 与 ONNX 对相同图片的预测是否足够一致。', advisory: false },
  mask_consistency: { label: '分割掩膜一致性', description: '比较 PT 与 ONNX 的掩膜边界差异；细小或细长目标可能对像素偏移敏感，该项不单独阻止发布。', advisory: true },
  independent_test_available: { label: '独立测试结果', description: '模型具有独立测试集评估结果，可用于判断泛化能力。', advisory: false },
  quality_recommended: { label: '推荐发布质量', description: '模型是否达到建议的测试证据和质量指标，该项不单独阻止发布。', advisory: true },
}

export interface ConsistencySampleDiagnostic {
  filename: string
  ptCount: number
  onnxCount: number
  failedPairs: number
  issues: string[]
  comparisonPath?: string
}

export interface ConsistencyDiagnostic {
  summary: string
  samples: ConsistencySampleDiagnostic[]
}

export interface GateDiagnosticItem extends ReleaseGate {
  expanded: boolean
  samples?: ConsistencySampleDiagnostic[]
}

export interface GateDiagnostics {
  summary: string
  hardFailures: number
  advisoryFailures: number
  items: GateDiagnosticItem[]
  reportUnavailable?: string
}

export function gateDefinition(key: string) {
  return definitions[key] ?? { label: key, description: '自定义模型检查项。', advisory: false }
}

function filename(path: string) {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? '未知图片'
}

function format(value: number) {
  return value.toFixed(3)
}

function sampleDiagnostic(sample: ModelGateSampleReport): ConsistencySampleDiagnostic {
  const issues: string[] = []
  if (sample.pt_count !== sample.onnx_count) {
    issues.push(`目标数量：PT ${sample.pt_count} 个，ONNX ${sample.onnx_count} 个`)
  }
  const minimumBox = Math.min(...sample.pairs.map((pair) => pair.box_iou))
  const maximumConfidenceDelta = Math.max(...sample.pairs.map((pair) => pair.confidence_delta))
  const maskValues = sample.pairs.flatMap((pair) => typeof pair.mask_iou === 'number' ? [pair.mask_iou] : [])
  const minimumMask = maskValues.length ? Math.min(...maskValues) : undefined
  if (sample.pairs.length && minimumBox < BOX_IOU_MIN) issues.push(`框 IoU ${format(minimumBox)}，低于要求 ${format(BOX_IOU_MIN)}`)
  if (sample.pairs.length && maximumConfidenceDelta > CONFIDENCE_DELTA_MAX) issues.push(`置信度差值 ${format(maximumConfidenceDelta)}，高于允许值 ${format(CONFIDENCE_DELTA_MAX)}`)
  if (minimumMask !== undefined && minimumMask < MASK_IOU_MIN) issues.push(`Mask IoU ${format(minimumMask)}，低于要求 ${format(MASK_IOU_MIN)}`)
  if (!issues.length && !sample.passed) issues.push('PT 与 ONNX 的预测配对不完整')
  return {
    filename: filename(sample.source),
    ptCount: sample.pt_count,
    onnxCount: sample.onnx_count,
    failedPairs: sample.pairs.filter((pair) => !pair.passed).length,
    issues,
    comparisonPath: sample.comparison_path ?? undefined,
  }
}

export function summarizeConsistency(report: ModelGateReport): ConsistencyDiagnostic {
  const failed = (report.samples ?? []).filter((sample) => !sample.passed)
  const countMismatch = failed.filter((sample) => sample.pt_count !== sample.onnx_count).length
  const boxMismatch = failed.filter((sample) => sample.pairs.some((pair) => pair.box_iou < BOX_IOU_MIN)).length
  const confidenceMismatch = failed.filter((sample) => sample.pairs.some((pair) => pair.confidence_delta > CONFIDENCE_DELTA_MAX)).length
  const maskMismatch = failed.filter((sample) => sample.pairs.some((pair) => typeof pair.mask_iou === 'number' && pair.mask_iou < MASK_IOU_MIN)).length
  const reasons = [
    countMismatch ? `${countMismatch} 张目标数量不一致` : '',
    boxMismatch ? `${boxMismatch} 张存在检测框差异` : '',
    confidenceMismatch ? `${confidenceMismatch} 张存在置信度差异` : '',
    maskMismatch ? `${maskMismatch} 张存在分割轮廓差异` : '',
  ].filter(Boolean)
  return {
    summary: failed.length ? `${failed.length} 张验证图片未通过：${reasons.join('，')}。` : '抽样图片的 PT 与 ONNX 预测一致。',
    samples: failed.map(sampleDiagnostic),
  }
}

export function summarizeMaskConsistency(report: ModelGateReport): ConsistencyDiagnostic {
  const failed = (report.samples ?? []).filter((sample) =>
    sample.mask_consistency === false
    || sample.pairs.some((pair) => pair.mask_passed === false || typeof pair.mask_iou === 'number' && pair.mask_iou < MASK_IOU_MIN),
  )
  const values = failed.flatMap((sample) =>
    sample.pairs.flatMap((pair) => typeof pair.mask_iou === 'number' ? [pair.mask_iou] : []),
  )
  const minimum = values.length ? Math.min(...values) : undefined
  return {
    summary: failed.length
      ? `${failed.length} 张图片存在掩膜边界差异${minimum === undefined ? '' : `，最低 Mask IoU ${format(minimum)}`}；该项用于提示 ONNX 掩膜保真度，不单独阻止发布。`
      : '抽样图片的 PT 与 ONNX 分割掩膜一致。',
    samples: failed.map(sampleDiagnostic),
  }
}

export function qualityRecommendation(report?: TrainingQualityReport) {
  const thresholds = report?.thresholds ?? {}
  const minimumImages = Number(thresholds.min_test_images ?? 30)
  const minimumInstances = Number(thresholds.min_test_instances_per_class ?? 10)
  if (!report || report.verdict === 'insufficient_evidence') {
    return {
      summary: '独立测试证据不足，当前指标还不能可靠代表真实效果。',
      recommendation: `建议至少准备 ${minimumImages} 张独立测试图片，并保证每个类别至少有 ${minimumInstances} 个测试实例后重新评估。`,
    }
  }
  if (report.verdict === 'needs_improvement') return { summary: '至少一项独立测试核心指标低于试用线。', recommendation: '建议检查标注质量、类别均衡和错误样本后重新训练。' }
  if (report.verdict === 'trial') return { summary: '模型达到试用线，但尚未达到推荐发布质量。', recommendation: '建议补充弱类别样本并复训，再用于正式业务。' }
  return { summary: '独立测试指标已达到推荐发布质量。', recommendation: '建议结合真实业务样本完成最终复核。' }
}

function gateValue(gate: ReleaseGate) {
  return gate.status === 'passed'
}

export function buildGateDiagnostics(model: ModelArtifact, reportResponse?: ModelGateReportApiResponse): GateDiagnostics {
  const hardFailures = model.gates.filter((gate) => !gate.advisory && !gateValue(gate)).length
  const advisoryFailures = model.gates.filter((gate) => gate.advisory && !gateValue(gate)).length
  const passed = model.gates.filter(gateValue).length
  const consistency = reportResponse?.available && reportResponse.report ? summarizeConsistency(reportResponse.report) : undefined
  const maskConsistency = reportResponse?.available && reportResponse.report ? summarizeMaskConsistency(reportResponse.report) : undefined
  const quality = qualityRecommendation(model.qualityReport)
  const items = model.gates.map<GateDiagnosticItem>((gate) => {
    const definition = gateDefinition(gate.key)
    const failed = !gateValue(gate)
    const detail = gate.key === 'consistency' && failed && consistency
      ? consistency.summary
      : gate.key === 'mask_consistency' && failed && maskConsistency
        ? maskConsistency.summary
      : gate.key === 'quality_recommended'
        ? `${quality.summary}${gate.advisory ? ' 该项不单独阻止发布。' : ''}`
        : failed ? `${definition.description} 当前检查未通过。` : definition.description
    const samples = gate.key === 'consistency'
      ? consistency?.samples
      : gate.key === 'mask_consistency' ? maskConsistency?.samples : undefined
    return { ...gate, label: definition.label, advisory: definition.advisory, detail, expanded: failed, samples }
  })
  return {
    summary: `${passed} 项通过，${hardFailures} 项阻止发布，${advisoryFailures} 项质量建议未达标。`,
    hardFailures,
    advisoryFailures,
    items,
    reportUnavailable: reportResponse && !reportResponse.available ? '暂无诊断详情，请重新运行门禁。' : undefined,
  }
}

export function gateCompletionFeedback(model: ModelArtifact): { type: 'success' | 'warning'; message: string } {
  const hardFailures = model.gates.filter((gate) => !gate.advisory && !gateValue(gate)).length
  const advisoryFailures = model.gates.filter((gate) => gate.advisory && !gateValue(gate)).length
  if (hardFailures) return { type: 'warning', message: `门禁检查完成，发现 ${hardFailures} 项阻止发布的问题。` }
  if (advisoryFailures) return { type: 'warning', message: '硬门禁已通过，但模型质量尚未达到推荐线。' }
  return { type: 'success', message: '门禁检查完成，可以发布。' }
}
