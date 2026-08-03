import { useEffect, useRef, useState } from 'react'
import { Button, Drawer, Empty, Switch, Tabs, Tooltip, Typography } from 'antd'
import { Braces, ChevronLeft, ChevronRight, Download } from 'lucide-react'

import { api } from '../../api'
import type { InferenceRun } from '../../platform/types'
import {
  canNavigateInferenceResults,
  canInspectInferenceRawOutput,
  clampInferenceResultIndex,
  getInferencePreviewKind,
} from './inferencePresentation'

export interface InferenceResultViewerProps {
  run: InferenceRun
  showStructuredMasks: boolean
  onStructuredMasksChange: (checked: boolean) => void
}

function resultFilename(sourceName: string) {
  return sourceName.split(/[\\/]/).pop() || sourceName
}

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function InferenceResultViewer({
  run,
  showStructuredMasks,
  onStructuredMasksChange,
}: InferenceResultViewerProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const touchStartX = useRef<number | null>(null)
  const thumbnailRefs = useRef<Array<HTMLButtonElement | null>>([])
  const resultCount = run.results.length
  const navigable = canNavigateInferenceResults(run.mode, resultCount)
  const safeIndex = clampInferenceResultIndex(activeIndex, resultCount)
  const activeResult = run.results[safeIndex]

  useEffect(() => setActiveIndex(0), [run.id])
  useEffect(() => {
    setActiveIndex((current) => clampInferenceResultIndex(current, resultCount))
  }, [resultCount])
  useEffect(() => {
    if (!navigable) return
    thumbnailRefs.current[safeIndex]?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [navigable, safeIndex])

  if (!activeResult) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="推理完成，当前阈值下未产生结果项" />
  }

  const selectResult = (index: number) => setActiveIndex(clampInferenceResultIndex(index, resultCount))
  const previewKind = getInferencePreviewKind(run.mode, activeResult.mediaPath)
  const mediaUrl = activeResult.mediaPath ? api.getArtifactUrl(activeResult.mediaPath) : undefined
  const sourceUrl = api.getArtifactUrl(activeResult.sourceName)
  const polygons = activeResult.detectionItems.filter((detection) => detection.polygon && detection.polygon.length >= 6)
  const filename = resultFilename(activeResult.sourceName)
  const rawOutputAvailable = canInspectInferenceRawOutput(activeResult.rawOnnxOutput, activeResult.rawOnnxOutputError)
  const parsedPayload = {
    source: activeResult.sourceName,
    detections: activeResult.detectionItems,
    inference_ms: activeResult.durationMs,
    media_path: activeResult.mediaPath ?? null,
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!navigable) return
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      selectResult(safeIndex - 1)
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      selectResult(safeIndex + 1)
    }
  }

  const handleTouchEnd = (event: React.TouchEvent<HTMLDivElement>) => {
    if (!navigable || touchStartX.current === null) return
    const distance = event.changedTouches[0].clientX - touchStartX.current
    touchStartX.current = null
    if (Math.abs(distance) < 48) return
    selectResult(distance > 0 ? safeIndex - 1 : safeIndex + 1)
  }

  return <div
    className="inference-result-viewer"
    tabIndex={navigable ? 0 : -1}
    aria-label={navigable ? `批量推理结果，当前第 ${safeIndex + 1} 张，共 ${resultCount} 张` : '推理结果'}
    onKeyDown={handleKeyDown}
  >
    <div
      className="inference-result-media"
      onTouchStart={(event) => { touchStartX.current = event.touches[0].clientX }}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={() => { touchStartX.current = null }}
    >
      {previewKind === 'image' && mediaUrl && (showStructuredMasks && polygons.length ? <div className="inference-image-stage">
        <img src={sourceUrl} alt={`${filename} 原图`} />
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="结构化分割掩膜">
          {polygons.map((detection, index) => <polygon
            key={`${detection.classId}-${index}`}
            points={detection.polygon!.reduce<string[]>((points, value, pointIndex) => pointIndex % 2 === 0
              ? [...points, `${value * 100},${detection.polygon![pointIndex + 1] * 100}`]
              : points, []).join(' ')}
          />)}
        </svg>
      </div> : <img src={mediaUrl} alt={`${filename} 推理结果预览`} />)}
      {previewKind === 'video' && mediaUrl && <video src={mediaUrl} controls preload="metadata" playsInline />}
      {previewKind === 'none' && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次结果没有可预览媒体" />}
    </div>

    <div className="inference-result-toolbar">
      <div className="inference-result-meta">
        <strong title={filename}>{filename}</strong>
        <span>{activeResult.summary} · 推理 {activeResult.durationMs.toFixed(1)} ms</span>
      </div>
      <div className="inference-result-actions">
        {run.mode !== 'video' && <label className="inference-mask-toggle">
          <Switch size="small" checked={showStructuredMasks} onChange={onStructuredMasksChange} />
          <span>结构化掩膜</span>
        </label>}
        {navigable && <div className="inference-result-pagination" aria-label="结果切换">
          <span>{safeIndex + 1} / {resultCount}</span>
          <Tooltip title="上一张">
            <Button
              icon={<ChevronLeft size={16} />}
              aria-label="上一张结果"
              disabled={safeIndex === 0}
              onClick={() => selectResult(safeIndex - 1)}
            />
          </Tooltip>
          <Tooltip title="下一张">
            <Button
              icon={<ChevronRight size={16} />}
              aria-label="下一张结果"
              disabled={safeIndex === resultCount - 1}
              onClick={() => selectResult(safeIndex + 1)}
            />
          </Tooltip>
        </div>}
        {mediaUrl && <Button icon={<Download size={15} />} href={mediaUrl} target="_blank">打开当前标注产物</Button>}
        <Button icon={<Braces size={15} />} onClick={() => setInspectorOpen(true)}>查看原始结构</Button>
      </div>
    </div>

    {navigable && <div className="inference-thumbnail-rail" aria-label="推理结果缩略图">
      {run.results.map((result, index) => {
        const thumbnailUrl = result.mediaPath ? api.getArtifactUrl(result.mediaPath) : undefined
        const thumbnailName = resultFilename(result.sourceName)
        return <Tooltip key={`${result.sourceName}-${index}`} title={thumbnailName}>
          <button
            ref={(element) => { thumbnailRefs.current[index] = element }}
            type="button"
            className="inference-thumbnail"
            aria-label={`查看第 ${index + 1} 张结果：${thumbnailName}`}
            aria-current={index === safeIndex ? 'true' : undefined}
            onClick={() => selectResult(index)}
          >
            {thumbnailUrl ? <img src={thumbnailUrl} alt="" loading="lazy" /> : <span className="inference-thumbnail-empty">无预览</span>}
            <span className="inference-thumbnail-index">{index + 1}</span>
          </button>
        </Tooltip>
      })}
    </div>}
    <Drawer title="推理原始结构" open={inspectorOpen} onClose={() => setInspectorOpen(false)} width={640} destroyOnHidden>
      <Tabs items={[
        {
          key: 'parsed',
          label: '解析后数据',
          children: <>
            <Typography.Paragraph type="secondary">平台用于绘制框、掩膜和统计信息的标准化结果。</Typography.Paragraph>
            <Button icon={<Download size={15} />} onClick={() => downloadJson(`${filename}.parsed.json`, parsedPayload)}>下载 JSON</Button>
            <Typography.Paragraph copyable={{ text: JSON.stringify(parsedPayload, null, 2) }}>
              <pre>{JSON.stringify(parsedPayload, null, 2)}</pre>
            </Typography.Paragraph>
          </>,
        },
        {
          key: 'raw-onnx',
          label: '原始 ONNX 输出',
          children: rawOutputAvailable && activeResult.rawOnnxOutput ? <>
            <Typography.Paragraph type="secondary">每个输出节点保留形状、范围和前 {activeResult.rawOnnxOutput.previewLimit} 个原始数值；完整张量不会写入结果文件。</Typography.Paragraph>
            <Button icon={<Download size={15} />} onClick={() => downloadJson(`${filename}.raw-onnx.json`, activeResult.rawOnnxOutput)}>下载 JSON</Button>
            <Typography.Paragraph copyable={{ text: JSON.stringify(activeResult.rawOnnxOutput, null, 2) }}>
              <pre>{JSON.stringify(activeResult.rawOnnxOutput, null, 2)}</pre>
            </Typography.Paragraph>
          </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={activeResult.rawOnnxOutputError ?? '该历史推理记录未保存原始 ONNX 输出。'} />,
        },
      ]} />
    </Drawer>
  </div>
}
