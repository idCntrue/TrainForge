import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { InferenceRun } from '../../platform/types'
import { InferenceResultViewer } from './InferenceResultViewer'

const results = [
  {
    sourceName: 'uploads/first.jpg',
    detections: 2,
    detectionItems: [],
    durationMs: 12.4,
    summary: '2 个目标',
    mediaPath: 'inference/first.jpg',
  },
  {
    sourceName: 'uploads/second.jpg',
    detections: 1,
    detectionItems: [],
    durationMs: 9.8,
    summary: '1 个目标',
    mediaPath: 'inference/second.jpg',
  },
]

function createRun(mode: InferenceRun['mode']): InferenceRun {
  return {
    id: `run-${mode}`,
    mode,
    task: mode === 'video' ? 'detect' : 'segment',
    modelId: 'model-1',
    runtime: 'pt',
    status: 'completed',
    confidence: 0.25,
    createdAt: '2026-07-23T08:00:00Z',
    results: mode === 'image' ? results.slice(0, 1) : mode === 'video' ? [{ ...results[0], mediaPath: 'inference/result.mp4' }] : results,
  }
}

function render(mode: InferenceRun['mode']) {
  return renderToStaticMarkup(
    <InferenceResultViewer
      run={createRun(mode)}
      showStructuredMasks={false}
      onStructuredMasksChange={vi.fn()}
    />,
  )
}

describe('InferenceResultViewer', () => {
  it('presents batch results as one active image with horizontal result navigation', () => {
    const html = render('batch')

    expect(html).toContain('inference-result-viewer')
    expect(html).toContain('1 / 2')
    expect(html).toContain('aria-label="上一张结果"')
    expect(html).toContain('aria-label="下一张结果"')
    expect(html).toContain('inference-thumbnail-rail')
    expect(html).toContain('aria-current="true"')
    expect(html).toContain('first.jpg')
    expect(html).toContain('打开当前标注产物')
  })

  it('hides batch navigation for a single image', () => {
    const html = render('image')

    expect(html).not.toContain('inference-thumbnail-rail')
    expect(html).not.toContain('aria-label="上一张结果"')
    expect(html).toContain('first.jpg')
  })

  it('keeps video results in the native player without image controls', () => {
    const html = render('video')

    expect(html).toContain('<video')
    expect(html).not.toContain('inference-thumbnail-rail')
    expect(html).not.toContain('结构化掩膜')
  })
})
