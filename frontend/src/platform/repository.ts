import { api } from '../api'
import { createApiPlatformRepository } from './apiPlatformRepository'
import { createApiTrainingRepository } from './apiTrainingRepository'

const apiRepository = createApiPlatformRepository(api)
const trainingRepository = createApiTrainingRepository(api)

export const platformRepository = {
  ...apiRepository,
  ...trainingRepository,
}
