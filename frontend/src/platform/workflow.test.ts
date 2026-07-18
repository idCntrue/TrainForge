import { describe, expect, it } from 'vitest'

import { recommendNextAction } from './workflow'

describe('recommendNextAction', () => {
  it.each([
    [{ tasks: 0, dataSources: 0, datasetReleases: 0, trainingRuns: 0, models: 0, publishedModels: 0 }, 'tasks'],
    [{ tasks: 1, dataSources: 0, datasetReleases: 0, trainingRuns: 0, models: 0, publishedModels: 0 }, 'videos'],
    [{ tasks: 1, dataSources: 1, datasetReleases: 0, trainingRuns: 0, models: 0, publishedModels: 0 }, 'review'],
    [{ tasks: 1, dataSources: 1, datasetReleases: 1, trainingRuns: 0, models: 0, publishedModels: 0 }, 'training'],
    [{ tasks: 1, dataSources: 1, datasetReleases: 1, trainingRuns: 1, models: 0, publishedModels: 0 }, 'training'],
    [{ tasks: 1, dataSources: 1, datasetReleases: 1, trainingRuns: 1, models: 1, publishedModels: 0 }, 'models'],
    [{ tasks: 1, dataSources: 1, datasetReleases: 1, trainingRuns: 1, models: 1, publishedModels: 1 }, 'inference'],
  ])('maps platform state to the next useful page', (totals, expectedView) => {
    expect(recommendNextAction(totals).view).toBe(expectedView)
  })
})
