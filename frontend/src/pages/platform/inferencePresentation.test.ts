import { describe, expect, it } from 'vitest'

import {
  canNavigateInferenceResults,
  clampInferenceResultIndex,
  getInferencePreviewKind,
  selectInitialInferenceModel,
  selectModelForTask,
} from './inferencePresentation'

const publishedModels = [
  { id: 'segment-model', task: 'segment' as const },
  { id: 'detect-model', task: 'detect' as const },
]

describe('inference model selection', () => {
  it('selects the available segment model when detect has no published model', () => {
    expect(selectInitialInferenceModel(publishedModels.slice(0, 1), 'detect')).toEqual({
      task: 'segment',
      modelId: 'segment-model',
    })
  })

  it('keeps detect selected when a published detect model exists', () => {
    expect(selectInitialInferenceModel(publishedModels, 'detect')).toEqual({
      task: 'detect',
      modelId: 'detect-model',
    })
  })

  it('keeps the preferred task without selecting a model when none are published', () => {
    expect(selectInitialInferenceModel([], 'detect')).toEqual({
      task: 'detect',
      modelId: undefined,
    })
  })

  it('selects only a model compatible with the requested task', () => {
    expect(selectModelForTask(publishedModels, 'segment')).toBe('segment-model')
    expect(selectModelForTask(publishedModels.slice(1), 'segment')).toBeUndefined()
  })
})

describe('inference result preview', () => {
  it('does not render media when the runner returned no artifact', () => {
    expect(getInferencePreviewKind('image', undefined)).toBe('none')
  })

  it('renders video runs with native video controls', () => {
    expect(getInferencePreviewKind('video', 'inference/result.mp4')).toBe('video')
  })

  it('renders image and batch runs as images', () => {
    expect(getInferencePreviewKind('image', 'inference/result.jpg')).toBe('image')
    expect(getInferencePreviewKind('batch', 'inference/result.jpg')).toBe('image')
  })
})

describe('inference result navigation', () => {
  it('clamps the active result to the available range', () => {
    expect(clampInferenceResultIndex(-1, 3)).toBe(0)
    expect(clampInferenceResultIndex(1, 3)).toBe(1)
    expect(clampInferenceResultIndex(5, 3)).toBe(2)
    expect(clampInferenceResultIndex(5, 0)).toBe(0)
  })

  it('only enables navigation for multi-image batch results', () => {
    expect(canNavigateInferenceResults('batch', 3)).toBe(true)
    expect(canNavigateInferenceResults('batch', 1)).toBe(false)
    expect(canNavigateInferenceResults('image', 3)).toBe(false)
    expect(canNavigateInferenceResults('video', 3)).toBe(false)
  })
})
