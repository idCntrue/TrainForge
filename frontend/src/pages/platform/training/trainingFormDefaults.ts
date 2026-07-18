import type { CreateTrainingRunInput } from '../../../platform/types'

export const trainingFormInitialValues: Partial<CreateTrainingRunInput> = {
  task: 'detect',
  epochs: 100,
  batch: 2,
  imageSize: 320,
  device: 'cpu',
  presetId: 'cpu-balanced',
  augmentation: {
    mosaic: 1.0,
    mixup: 0.0,
    copy_paste: 0.0,
    degrees: 0.0,
    translate: 0.1,
    scale: 0.5,
    fliplr: 0.5,
    hsv_h: 0.015,
    hsv_s: 0.7,
    hsv_v: 0.4,
  },
}
