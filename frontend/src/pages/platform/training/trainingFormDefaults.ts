import type { CreateTrainingRunInput } from '../../../platform/types'

export const trainingFormInitialValues: Partial<CreateTrainingRunInput> = {
  task: 'detect',
  epochs: 150,
  batch: 2,
  imageSize: 640,
  device: 'cpu',
  presetId: 'cpu-balanced',
  patience: 25,
  optimizer: 'auto',
  closeMosaic: 10,
  augmentProfile: 'conservative',
  augmentation: {
    mosaic: 0.5,
    mixup: 0.0,
    copy_paste: 0.0,
    degrees: 5.0,
    translate: 0.1,
    scale: 0.3,
    fliplr: 0.0,
    hsv_h: 0.01,
    hsv_s: 0.5,
    hsv_v: 0.3,
  },
}
