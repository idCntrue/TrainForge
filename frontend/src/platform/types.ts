export type TaskType = 'detect' | 'segment' | 'classify' | 'pose' | 'obb'
export type TrainingStatus = 'queued' | 'running' | 'evaluating' | 'exporting' | 'verifying' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
export type ModelStatus = 'candidate' | 'published' | 'blocked' | 'archived'
export type InferenceMode = 'image' | 'batch' | 'video'
export type InferenceRuntime = 'pt' | 'onnx'

export interface TrainingMetrics {
  primary?: number
  primaryLabel: string
  precision?: number
  recall?: number
  boxMap?: number
  maskMap?: number
}

export interface TrainingRun {
  id: string
  name: string
  task: TaskType
  status: TrainingStatus
  phase: string
  progress: number
  epoch: number
  epochs: number
  datasetReleaseId: string
  datasetName: string
  baseModel: string
  batch: number
  imageSize: number
  device: string
  createdAt: string
  duration: string
  metrics: TrainingMetrics
  logs: string[]
  selectedClasses: string[]
  classAliases: Record<string, string>
  sourceRunId?: string
  executionMode: 'train' | 'evaluate_existing'
  presetId: 'custom' | 'smoke' | 'cpu-balanced' | 'gpu-quality'
  patience: number
  optimizer: 'auto' | 'SGD' | 'Adam' | 'AdamW'
  closeMosaic: number
  augmentProfile: 'conservative' | 'standard'
  augmentation: import('../api').TrainingAugmentationOptions
}

export interface CreateTrainingRunInput {
  name: string
  task: TaskType
  datasetReleaseId: string
  baseModel: string
  epochs: number
  batch: number
  imageSize: number
  device: string
  selectedClasses?: string[]
  classAliases?: Record<string, string>
  presetId?: 'custom' | 'smoke' | 'cpu-balanced' | 'gpu-quality'
  patience?: number
  optimizer?: 'auto' | 'SGD' | 'Adam' | 'AdamW'
  closeMosaic?: number
  augmentProfile?: 'conservative' | 'standard'
  augmentation?: Partial<import('../api').TrainingAugmentationOptions>
}

export interface TrainingFilters {
  task?: TaskType
  status?: TrainingStatus
}

export interface ReleaseGate {
  key: string
  label: string
  status: 'passed' | 'running' | 'blocked'
  detail: string
  advisory: boolean
}

export interface ModelArtifact {
  id: string
  name: string
  version: string
  task: TaskType
  status: ModelStatus
  datasetReleaseId: string
  datasetName: string
  trainingRunId: string
  primaryMetric: number
  primaryMetricLabel: string
  sizeMb: number
  formats: string[]
  publishedAt?: string
  createdAt: string
  baseModel: string
  weightHash: string
  environment: string
  gateReportPath?: string
  gates: ReleaseGate[]
  qualityReport?: import('../api').TrainingQualityReport
}

export interface ModelFilters {
  task?: TaskType
  status?: ModelStatus
}

export interface DashboardData {
  gpu?: { name: string; memoryUsedGb: number; memoryTotalGb: number; utilization: number; temperature: number }
  totals: { tasks: number; dataSources: number; datasetReleases: number; trainingRuns: number; models: number; publishedModels: number; inferenceRuns: number }
  activeRun?: TrainingRun
  recentRuns: TrainingRun[]
  recentModels: ModelArtifact[]
}

export interface CreateInferenceRunInput {
  mode: InferenceMode
  task: TaskType
  modelId: string
  runtime: InferenceRuntime
  confidence: number
  sourceNames: string[]
}

export interface InferenceResult {
  sourceName: string
  detections: number
  detectionItems: InferenceDetection[]
  durationMs: number
  summary: string
  mediaPath?: string
}

export interface InferenceDetection {
  classId: number
  className: string
  confidence: number
  box: number[]
  polygon?: number[]
}

export interface InferenceRun {
  id: string
  mode: InferenceMode
  task: TaskType
  modelId: string
  runtime: InferenceRuntime
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
  confidence: number
  createdAt: string
  results: InferenceResult[]
}

export interface PlatformRepository {
  getDashboard(): Promise<DashboardData>
  listTrainingRuns(filters: TrainingFilters): Promise<TrainingRun[]>
  getTrainingRun(id: string): Promise<TrainingRun | undefined>
  createTrainingRun(input: CreateTrainingRunInput): Promise<TrainingRun>
  cancelTrainingRun(id: string): Promise<TrainingRun>
  deleteTrainingRun(id: string, deleteArtifacts: boolean, cascade?: boolean): Promise<void>
  listModels(filters: ModelFilters): Promise<ModelArtifact[]>
  getModel(id: string): Promise<ModelArtifact | undefined>
  createInferenceRun(input: CreateInferenceRunInput): Promise<InferenceRun>
}

export type TrainingRepository = Pick<PlatformRepository, 'listTrainingRuns' | 'getTrainingRun' | 'createTrainingRun' | 'cancelTrainingRun' | 'deleteTrainingRun'> & {
  refreshTrainingRun(id: string): Promise<TrainingRun>
}
