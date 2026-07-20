import type { CreateTrainingRunInput, TaskType } from '../../../platform/types'

type PresetId = NonNullable<CreateTrainingRunInput['presetId']>

const conservative = { mosaic: 0.5, mixup: 0, copy_paste: 0, degrees: 5, translate: 0.1, scale: 0.3, fliplr: 0, hsv_h: 0.01, hsv_s: 0.5, hsv_v: 0.3 }
const standard = { mosaic: 1, mixup: 0, copy_paste: 0, degrees: 0, translate: 0.1, scale: 0.5, fliplr: 0.5, hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4 }

const presetValues = {
  smoke: { epochs: 10, imageSize: 320, patience: 5, optimizer: 'auto', closeMosaic: 2, augmentProfile: 'conservative', augmentation: conservative },
  'cpu-balanced': { epochs: 150, imageSize: 640, patience: 25, optimizer: 'auto', closeMosaic: 10, augmentProfile: 'conservative', augmentation: conservative },
  'gpu-quality': { epochs: 200, imageSize: 640, patience: 30, optimizer: 'auto', closeMosaic: 10, augmentProfile: 'standard', augmentation: standard },
} as const

export function strategyPatchForPreset(presetId: PresetId, task: TaskType, device: string, current: Partial<CreateTrainingRunInput> = {}): Partial<CreateTrainingRunInput> {
  if (presetId === 'custom') return { ...current, presetId }
  const isCpu = device.toLowerCase().startsWith('cpu')
  if (presetId === 'gpu-quality' && isCpu) throw new Error('GPU 高质量预设需要 CUDA 设备')
  const batch = presetId === 'smoke' ? 1 : isCpu ? (task === 'segment' ? 1 : 2) : 8
  return { presetId, batch, ...presetValues[presetId], augmentation: { ...presetValues[presetId].augmentation } }
}

const strategyRoots = new Set(['epochs', 'batch', 'imageSize', 'patience', 'optimizer', 'closeMosaic', 'augmentProfile', 'augmentation'])

export function isStrategyField(path: Array<string | number>): boolean {
  return typeof path[0] === 'string' && strategyRoots.has(path[0])
}

export function validateCloseMosaic(epochs?: number, closeMosaic?: number): string | undefined {
  if (epochs !== undefined && closeMosaic !== undefined && closeMosaic > epochs) return '关闭 Mosaic 轮次不能大于总轮次'
  return undefined
}
