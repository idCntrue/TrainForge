import { describe, expect, it } from 'vitest'
import { isStrategyField, strategyPatchForPreset, validateCloseMosaic } from './trainingStrategyForm'

describe('training strategy form', () => {
  it('matches the server presets and chooses a resource-safe batch', () => {
    expect(strategyPatchForPreset('smoke', 'detect', 'cpu')).toMatchObject({ epochs: 10, batch: 1, imageSize: 320, patience: 5, optimizer: 'auto', closeMosaic: 2, augmentProfile: 'conservative' })
    expect(strategyPatchForPreset('cpu-balanced', 'detect', 'cpu').batch).toBe(2)
    expect(strategyPatchForPreset('cpu-balanced', 'segment', 'cpu').batch).toBe(1)
    expect(strategyPatchForPreset('gpu-quality', 'segment', '0')).toMatchObject({ epochs: 200, batch: 8, imageSize: 640, patience: 30, closeMosaic: 10, augmentProfile: 'standard' })
  })

  it('rejects the GPU quality preset on CPU', () => {
    expect(() => strategyPatchForPreset('gpu-quality', 'detect', 'cpu')).toThrow('GPU')
  })

  it('identifies fields whose manual edits make a preset custom', () => {
    expect(isStrategyField(['patience'])).toBe(true)
    expect(isStrategyField(['augmentation', 'mosaic'])).toBe(true)
    expect(isStrategyField(['name'])).toBe(false)
  })

  it('allows disabled early stopping and validates close mosaic against epochs', () => {
    expect(strategyPatchForPreset('custom', 'detect', 'cpu', { patience: 0 }).patience).toBe(0)
    expect(validateCloseMosaic(5, 6)).toBe('关闭 Mosaic 轮次不能大于总轮次')
    expect(validateCloseMosaic(5, 5)).toBeUndefined()
    expect(validateCloseMosaic(5, 0)).toBeUndefined()
  })
})
