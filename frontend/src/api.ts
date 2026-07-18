import { createRequestId } from './requestId'

export interface DashboardSummary {
  tasks: number
  video_collections: number
  video_assets: number
  frame_batches: number
  annotation_exports: number
  dataset_releases: number
}

export interface TaskSummary {
  id: string
  task_type: 'detect' | 'segment'
  annotation_format: string
  classes: string[]
  class_display_names: Record<string, string>
  created_at: string
}

export interface CreateTaskRequest {
  id: string
  task_type: 'detect' | 'segment'
  classes: string[]
  class_display_names?: Record<string, string>
}

export interface VideoCollectionSummary {
  id: string
  task_id: string
  asset_count: number
  total_size_bytes: number
  created_at: string
}

export interface DatasetReleaseSummary {
  id: string
  task_id: string
  annotation_export_id: string
  display_name: string
  version: string
  status: string
  release_path: string
  created_at: string
  requested_ratios: { train: number; val: number; test: number } | null
  actual_ratios: Record<string, number>
  split_counts: Record<string, number>
  split_seed: number | null
  grouping_strategy: string | null
}

export interface HealthStatus {
  status: string
  storage_root: string
}

export interface JobStatus {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  payload: any
}

export interface FrameAssetSummary {
  id: string
  filename: string
  stored_path: string
  status: 'candidate' | 'selected' | 'rejected' | 'duplicate'
  rejection_reason?: string
  timestamp_ms: number
  frame_index: number
  video_id: string
}

export interface FramePageResponse {
  items: FrameAssetSummary[]
  page: number
  page_size: number
  total: number
  status_counts: { candidate: number; selected: number; rejected: number; duplicate: number }
}

export interface RecycledFrameSummary {
  id: string
  batch_id: string
  filename: string
  stored_path: string
  size_bytes: number
  has_annotation: boolean
  trashed_at: string
  purge_after: string
}

export interface RecycledFramePage {
  items: RecycledFrameSummary[]
  page: number
  page_size: number
  total: number
}

export interface RecycleBinSummary {
  item_count: number
  total_bytes: number
  earliest_purge_after: string | null
}

export interface DuplicateGroupSummary {
  canonical: string
  duplicates: string[]
}

export type TrainingRunStatus = 'queued' | 'running' | 'evaluating' | 'exporting' | 'verifying' | 'completed' | 'failed' | 'cancelled' | 'interrupted'

export interface TrainingAugmentationOptions {
  mosaic: number
  mixup: number
  copy_paste: number
  degrees: number
  translate: number
  scale: number
  fliplr: number
  hsv_h: number
  hsv_s: number
  hsv_v: number
}

export interface TrainingRunApiResponse {
  id: string
  name: string
  task_type: 'detect' | 'segment'
  dataset_release_id: string
  base_model: string
  epochs: number
  batch: number
  image_size: number
  device: string
  status: TrainingRunStatus
  progress: number
  phase: string
  message: string
  pid: number | null
  run_directory: string | null
  created_at: string
  updated_at: string
  finished_at: string | null
  exit_code: number | null
  epoch: number | null
  total_epochs: number | null
  metrics: Record<string, number | null>
  artifacts: Record<string, string | null>
  selected_classes: string[]
  class_aliases: Record<string, string>
  source_run_id: string | null
  execution_mode: 'train' | 'evaluate_existing'
  retry_strategy: string | null
  preset_id: 'custom' | 'smoke' | 'cpu-balanced' | 'gpu-quality'
  patience: number
  optimizer: string
  close_mosaic: number
  augment_profile: 'conservative' | 'standard'
  augmentation: TrainingAugmentationOptions
}

export interface TrainingRecoveryOptions {
  can_safe_retry: boolean
  can_evaluate_best: boolean
  best_weight_path: string | null
  preserved_artifact_count: number
  reason: string
}

export interface TrainingFailureDiagnostic {
  schema_version: number
  code: string
  summary: string
  action: string
  technical_message: string
  exception_type: string | null
  traceback: string | null
  exit_code: number | null
  failure_phase: string
  failure_scope: string
  last_successful_epoch: number | null
  total_epochs: number | null
  occurred_at: string
  evidence: string[]
  resource_snapshot: Record<string, number | null>
  recoverability: TrainingRecoveryOptions | null
}

export interface DatasetQualityReport {
  split_images: Record<string, number>
  split_instances: Record<string, number>
  class_instances: Record<string, Record<string, number>>
  empty_label_files: string[]
  missing_label_files: string[]
  imbalance_ratio: number | null
  blockers: string[]
  warnings: string[]
}

export interface TestMetricsReport {
  split: 'test'
  task_type: string
  overall: Record<string, number | null>
  per_class: Array<{ class_id: number; class_name: string; precision: number | null; recall: number | null; map50: number | null; map50_95: number | null }>
}

export interface TrainingQualityReport {
  verdict: 'insufficient_evidence' | 'needs_improvement' | 'trial' | 'ready'
  confidence: 'low' | 'medium' | 'high'
  reasons: string[]
  recommendations: string[]
  best_epoch: number | null
  weakest_classes: TestMetricsReport['per_class']
  thresholds: Record<string, unknown>
}

export interface TrainingEpochMetrics {
  epoch: number
  time?: number
  [key: string]: number | undefined
}

export interface TrainingArtifactApiResponse {
  key: string
  name: string
  kind: 'image' | 'weight' | 'file'
  path: string
  size_bytes: number
}

export interface TrainingRunDetailsApiResponse {
  run_id: string
  configuration: { name: string; task_type: string; dataset_release_id: string; base_model: string; epochs: number; batch: number; image_size: number; device: string; selected_classes: string[]; class_aliases: Record<string, string> }
  timing: { epoch_seconds: number | null; eta_seconds: number | null }
  split_distribution: { requested_ratios: Record<string, number> | null; actual_ratios: Record<string, number>; split_counts: Record<string, number>; split_seed: number | null; grouping_strategy: string | null }
  epoch_history: TrainingEpochMetrics[]
  latest_metrics: Record<string, number | null>
  artifacts: TrainingArtifactApiResponse[]
  logs: string[]
  warnings: string[]
  failure_diagnostic: TrainingFailureDiagnostic | null
  recovery_options: TrainingRecoveryOptions | null
  related_runs: Array<{ id: string; status: string; name: string; source_run_id: string | null; execution_mode: string; retry_strategy: string | null }>
  dataset_quality: DatasetQualityReport | null
  test_metrics: TestMetricsReport | null
  quality_report: TrainingQualityReport | null
}

export interface CreateTrainingRunApiRequest {
  name: string
  task_type: string
  dataset_release_id: string
  base_model: string
  epochs: number
  batch: number
  image_size: number
  device: string
  selected_classes: string[]
  class_aliases: Record<string, string>
  preset_id?: 'custom' | 'smoke' | 'cpu-balanced' | 'gpu-quality'
  patience?: number
  optimizer?: string
  close_mosaic?: number
  augment_profile?: 'conservative' | 'standard'
  augmentation?: Partial<TrainingAugmentationOptions>
}

export interface TrainingApiClient {
  listTrainingRuns(): Promise<TrainingRunApiResponse[]>
  getTrainingRun(id: string): Promise<TrainingRunApiResponse>
  createTrainingRun(input: CreateTrainingRunApiRequest): Promise<TrainingRunApiResponse>
  refreshTrainingRun(id: string): Promise<TrainingRunApiResponse>
  cancelTrainingRun(id: string): Promise<TrainingRunApiResponse>
  deleteTrainingRun(id: string, deleteArtifacts: boolean, cascade?: boolean): Promise<void>
  retryTrainingRun(id: string, input: { strategy: 'safe'; request_id: string }): Promise<TrainingRunApiResponse>
  recoverTrainingEvaluation(id: string): Promise<TrainingRunApiResponse>
}

export interface ModelVersionApiResponse {
  id: string
  name: string
  version: string
  task_type: 'detect' | 'segment'
  training_run_id: string
  dataset_release_id: string
  selected_classes: string[]
  class_aliases: Record<string, string>
  metrics: Record<string, number | null>
  status: 'candidate' | 'published' | 'blocked' | 'archived'
  gates: Record<string, boolean>
  artifacts: Record<string, { path: string; sha256: string; size_bytes: number }>
  environment: Record<string, string>
  gate_report_path: string | null
  created_at: string
  updated_at: string
  published_at: string | null
  archived_at: string | null
  quality_report?: TrainingQualityReport | null
}

export interface InferenceRunApiResponse {
  id: string
  model_version_id: string
  mode: 'image' | 'batch' | 'video'
  runtime: 'pt' | 'onnx'
  sources: string[]
  confidence: number
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
  progress: number
  message: string
  output_directory: string | null
  result_path: string | null
  result: { items?: Array<{ source: string; detections: InferenceDetectionApiResponse[]; speed?: { inference?: number }; media_path?: string | null }>; media?: string[] } | null
  created_at: string
  updated_at: string
  finished_at: string | null
}

export interface InferenceDetectionApiResponse {
  class_id: number
  class_name: string
  confidence: number
  box: number[]
  polygon?: number[]
}

export interface CreateInferenceRunApiRequest {
  model_version_id: string
  mode: 'image' | 'batch' | 'video'
  runtime: 'pt' | 'onnx'
  sources: string[]
  confidence: number
}

export type AnnotationStatus = 'pending' | 'annotated' | 'reviewed'
export type AnnotationTool = 'select' | 'box' | 'polygon' | 'sam'

export interface AnnotationShapeApiResponse {
  id: string
  class_id: number
  class_name: string
  shape_type: 'box' | 'polygon'
  coordinates: number[]
  source: 'manual' | 'sam2'
  created_at: string
  updated_at: string
}

export interface AnnotationImageApiResponse {
  frame_id: string
  task_id: string
  task_type: 'detect' | 'segment'
  image_path: string
  width: number
  height: number
  status: AnnotationStatus
  revision: number
  classes: string[]
  shapes: AnnotationShapeApiResponse[]
  created_at: string
  updated_at: string
}

export interface AnnotationImageSummaryApiResponse {
  frame_id: string
  task_id: string
  task_type: 'detect' | 'segment'
  status: AnnotationStatus
  revision: number
  shape_count: number
  created_at: string
  updated_at: string
}

export interface AnnotationImagePageResponse {
  items: AnnotationImageSummaryApiResponse[]
  page: number
  page_size: number
  total: number
  status_counts: Record<AnnotationStatus, number>
}

export interface AnnotationSyncApiResponse {
  synced_count: number
  total_count: number
}

export interface AnnotationShapeMutation {
  revision: number
  class_id: number
  class_name: string
  shape_type: 'box' | 'polygon'
  coordinates: number[]
  source?: 'manual' | 'sam2'
}

export interface TrainingStorageErrorDetail {
  code: 'insufficient_training_storage'
  message: string
  free_gib: number
  free_percent: number
  required_gib: number
  required_percent: number
  failed_checks: Array<'absolute' | 'percentage'>
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

const API_BASE_URL = (import.meta as any).env?.VITE_API_BASE_URL ?? '/api'

async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`)
  } catch {
    throw new Error('API 服务未启动，请运行 scripts/start-ui.ps1')
  }
  if (!response.ok) throw new Error(`API 请求失败：HTTP ${response.status}`)
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new Error('API 返回了非 JSON 响应，请检查 8000 端口服务')
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: any): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error('API 服务未连接')
  }
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    const parsed = parseErrorResponse(errorText)
    const message = parsed.message || `API 请求失败：HTTP ${response.status}`
    if (parsed.detail && typeof parsed.detail === 'object' && !Array.isArray(parsed.detail)) {
      throw new ApiError(message, response.status, parsed.detail)
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function parseErrorResponse(errorText: string): { message: string; detail?: unknown } {
  try {
    const payload = JSON.parse(errorText) as { detail?: unknown }
    if (typeof payload.detail === 'string') return { message: payload.detail, detail: payload.detail }
    if (payload.detail && typeof payload.detail === 'object' && !Array.isArray(payload.detail)) {
      const detail = payload.detail as { message?: unknown }
      if (typeof detail.message === 'string') return { message: detail.message, detail: payload.detail }
    }
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail.flatMap((item) => {
        if (!item || typeof item !== 'object') return []
        const error = item as { loc?: unknown; msg?: unknown }
        const field = Array.isArray(error.loc) ? error.loc.at(-1) : undefined
        if (typeof error.msg !== 'string') return []
        return [typeof field === 'string' ? `${field}：${error.msg}` : error.msg]
      })
      if (messages.length) return { message: messages.join('；'), detail: payload.detail }
    }
    return { message: errorText, detail: payload.detail }
  } catch {
    return { message: errorText }
  }
}

function errorDetail(errorText: string): string {
  return parseErrorResponse(errorText).message
}

async function mutateJson<T>(method: 'PATCH' | 'PUT' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(errorText || `API request failed: HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function deleteResource(path: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: 'DELETE' })
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    const detail = errorDetail(errorText)
    throw new Error(detail || `API request failed: HTTP ${response.status}`)
  }
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form })
  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    throw new Error(errorText || `API request failed: HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function postFormWithProgress<T>(path: string, form: FormData, onProgress?: (percent: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', `${API_BASE_URL}${path}`)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.round(event.loaded / event.total * 100))
      }
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText) as T)
        } catch {
          reject(new Error('服务器返回了无法解析的上传结果'))
        }
        return
      }
      reject(new Error(errorDetail(request.responseText) || `API request failed: HTTP ${request.status}`))
    }
    request.onerror = () => reject(new Error('文件上传失败，请检查网络后重试'))
    request.send(form)
  })
}

export const api = {
  dashboard: () => getJson<DashboardSummary>('/dashboard'),
  tasks: () => getJson<TaskSummary[]>('/tasks'),
  createTask: (input: CreateTaskRequest) => postJson<TaskSummary>('/tasks', input),
  updateTask: (id: string, classDisplayNames: Record<string, string>) => mutateJson<TaskSummary>('PATCH', `/tasks/${id}`, { class_display_names: classDisplayNames }),
  deleteTask: (id: string, deleteArtifacts = true, cascade = false) => deleteResource(`/tasks/${id}?delete_artifacts=${deleteArtifacts}&cascade=${cascade}`),
  collections: () => getJson<VideoCollectionSummary[]>('/video-collections'),
  releases: () => getJson<DatasetReleaseSummary[]>('/dataset-releases'),
  health: () => getJson<HealthStatus>('/health'),
  listTrainingRuns: () => getJson<TrainingRunApiResponse[]>('/training-runs'),
  getTrainingRun: (id: string) => getJson<TrainingRunApiResponse>(`/training-runs/${id}`),
  getTrainingRunDetails: (id: string) => getJson<TrainingRunDetailsApiResponse>(`/training-runs/${id}/details`),
  createTrainingRun: (input: CreateTrainingRunApiRequest) => postJson<TrainingRunApiResponse>('/training-runs', input),
  createTrainingRunWithWeight: (input: CreateTrainingRunApiRequest, file: File, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('name', input.name)
    form.append('task_type', input.task_type)
    form.append('dataset_release_id', input.dataset_release_id)
    form.append('epochs', String(input.epochs))
    form.append('batch', String(input.batch))
    form.append('image_size', String(input.image_size))
    form.append('device', input.device)
    form.append('selected_classes', JSON.stringify(input.selected_classes))
    form.append('class_aliases', JSON.stringify(input.class_aliases))
    form.append('base_model_file', file)
    return postFormWithProgress<TrainingRunApiResponse>('/training-runs/upload', form, onProgress)
  },
  refreshTrainingRun: (id: string) => postJson<TrainingRunApiResponse>(`/training-runs/${id}/refresh`, {}),
  cancelTrainingRun: (id: string) => postJson<TrainingRunApiResponse>(`/training-runs/${id}/cancel`, {}),
  retryTrainingRun: (id: string, input: { strategy: 'safe'; request_id: string }) => postJson<TrainingRunApiResponse>(`/training-runs/${id}/retry`, input),
  recoverTrainingEvaluation: (id: string) => postJson<TrainingRunApiResponse>(`/training-runs/${id}/recover-evaluation`, {}),
  deleteTrainingRun: (id: string, deleteArtifacts = false, cascade = false) => deleteResource(`/training-runs/${id}?delete_artifacts=${deleteArtifacts}&cascade=${cascade}`),
  listModelVersions: () => getJson<ModelVersionApiResponse[]>('/model-versions'),
  createModelVersion: (input: { training_run_id: string; name: string; version: string }) => postJson<ModelVersionApiResponse>('/model-versions', input),
  runModelGates: (id: string) => postJson<ModelVersionApiResponse>(`/model-versions/${id}/gates`, {}),
  publishModel: (id: string) => postJson<ModelVersionApiResponse>(`/model-versions/${id}/publish`, {}),
  archiveModel: (id: string) => postJson<ModelVersionApiResponse>(`/model-versions/${id}/archive`, {}),
  deleteModel: (id: string, deleteArtifacts = false, cascade = false) => deleteResource(`/model-versions/${id}?delete_artifacts=${deleteArtifacts}&cascade=${cascade}`),
  listInferenceRuns: () => getJson<InferenceRunApiResponse[]>('/inference-runs'),
  getInferenceRun: (id: string) => getJson<InferenceRunApiResponse>(`/inference-runs/${id}`),
  createInferenceRun: (input: CreateInferenceRunApiRequest) => postJson<InferenceRunApiResponse>('/inference-runs', input),
  uploadInferenceRun: (input: Omit<CreateInferenceRunApiRequest, 'sources'>, files: File[], onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('model_version_id', input.model_version_id)
    form.append('mode', input.mode)
    form.append('runtime', input.runtime)
    form.append('confidence', String(input.confidence))
    files.forEach((file) => form.append('files', file))
    return postFormWithProgress<InferenceRunApiResponse>('/inference-runs/upload', form, onProgress)
  },
  refreshInferenceRun: (id: string) => postJson<InferenceRunApiResponse>(`/inference-runs/${id}/refresh`, {}),
  cancelInferenceRun: (id: string) => postJson<InferenceRunApiResponse>(`/inference-runs/${id}/cancel`, {}),
  deleteInferenceRun: (id: string, deleteArtifacts = false) => deleteResource(`/inference-runs/${id}?delete_artifacts=${deleteArtifacts}`),
  syncAnnotationImages: (taskId: string) => postJson<AnnotationSyncApiResponse>('/annotation-images/sync', { task_id: taskId }),
  listAnnotationImages: (taskId?: string, status?: AnnotationStatus, page = 1, pageSize = 30) => {
    const params = new URLSearchParams()
    if (taskId) params.set('task_id', taskId)
    if (status) params.set('status', status)
    params.set('page', String(page))
    params.set('page_size', String(pageSize))
    const query = params.toString()
    return getJson<AnnotationImagePageResponse>(`/annotation-images${query ? `?${query}` : ''}`)
  },
  getAnnotationImage: (frameId: string) => getJson<AnnotationImageApiResponse>(`/annotation-images/${encodeURIComponent(frameId)}`),
  getAnnotationImageUrl: (frameId: string) => `${API_BASE_URL}/annotation-images/${encodeURIComponent(frameId)}/content`,
  getAnnotationThumbnailUrl: (frameId: string) => `${API_BASE_URL}/annotation-images/${encodeURIComponent(frameId)}/thumbnail`,
  createAnnotationShape: (frameId: string, input: AnnotationShapeMutation) =>
    postJson<AnnotationImageApiResponse>(`/annotation-images/${frameId}/shapes`, input),
  updateAnnotationShape: (frameId: string, shapeId: string, input: AnnotationShapeMutation) =>
    mutateJson<AnnotationImageApiResponse>('PUT', `/annotation-images/${frameId}/shapes/${shapeId}`, input),
  deleteAnnotationShape: (frameId: string, shapeId: string, revision: number) =>
    mutateJson<AnnotationImageApiResponse>('DELETE', `/annotation-images/${frameId}/shapes/${shapeId}?revision=${revision}`),
  setAnnotationStatus: (frameId: string, revision: number, status: AnnotationStatus) =>
    postJson<AnnotationImageApiResponse>(`/annotation-images/${frameId}/status`, { revision, status }),
  suggestAnnotationWithSam: (frameId: string, input: { revision: number; class_id: number; class_name: string; model: 'sam2_t.pt' | 'sam2_s.pt'; point: [number, number] }) =>
    postJson<AnnotationImageApiResponse>(`/annotation-images/${frameId}/sam`, input),
  previewAnnotationWithSam: (frameId: string, input: { model: 'sam2_t.pt' | 'sam2_s.pt'; positive_points: [number, number][]; negative_points: [number, number][]; simplify: number }) =>
    postJson<{ polygon: number[]; model: string; model_was_loaded: boolean }>(`/annotation-images/${frameId}/sam/preview`, input),
  exportNativeAnnotations: (taskId: string, exportName: string) =>
    postJson<{ export_id: string; extracted_root: string; sample_count: number }>('/annotation-exports/native', { task_id: taskId, export_name: exportName }),
  getArtifactUrl: (path: string) => `${API_BASE_URL}/artifacts?path=${encodeURIComponent(path)}`,
  getAnnotationPackageUrl: (batchId: string) => `${API_BASE_URL}/annotation-packages/${encodeURIComponent(batchId)}/download`,

  // UI-2 new methods
  importVideos: (taskId: string, collectionId: string, sourceDir: string) =>
    postJson<{ job_id: string }>('/video-collections', { task_id: taskId, collection_id: collectionId, source_dir: sourceDir }),
  uploadVideos: (taskId: string, collectionId: string, files: File[], onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('task_id', taskId)
    form.append('collection_id', collectionId)
    files.forEach((file) => form.append('files', file))
    return postFormWithProgress<{ job_id: string; uploaded_count: number; filenames: string[] }>('/video-collections/upload', form, onProgress)
  },

  getJobStatus: (jobId: string) =>
    getJson<JobStatus>(`/jobs/${jobId}`),

  extractFrames: (collectionId: string, batchId: string, interval: number, quality: number) =>
    postJson<{ job_id: string }>('/frame-batches', { collection_id: collectionId, batch_id: batchId, interval, quality }),


  listBatches: () =>
    getJson<{ id: string; collection_id: string }[]>('/frame-batches'),
  deleteFrameBatch: (id: string, deleteArtifacts = false) => deleteResource(`/frame-batches/${id}?delete_artifacts=${deleteArtifacts}`),
  deleteVideoCollection: (id: string, deleteArtifacts = false, cascade = false) => deleteResource(`/video-collections/${id}?delete_artifacts=${deleteArtifacts}&cascade=${cascade}`),
  deleteDatasetRelease: (id: string, deleteArtifacts = false, cascade = false) => deleteResource(`/dataset-releases/${id}?delete_artifacts=${deleteArtifacts}&cascade=${cascade}`),
  uploadImages: (taskId: string, batchId: string, files: File[]) => {
    const form = new FormData()
    form.append('task_id', taskId)
    form.append('batch_id', batchId)
    files.forEach((file) => form.append('files', file))
    return postForm<{ collection_id: string; batch_id: string; imported_count: number; frames: FrameAssetSummary[] }>('/image-imports', form)
  },
  appendBatchImages: (batchId: string, files: File[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return postForm<{ batch_id: string; imported_count: number; skipped_count: number }>(`/frame-batches/${batchId}/images`, form)
  },
  appendBatchVideos: (batchId: string, files: File[], interval: number, quality: number, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('interval', String(interval))
    form.append('quality', String(quality))
    return postFormWithProgress<{ job_id: string; uploaded_count: number; filenames: string[] }>(
      `/frame-batches/${encodeURIComponent(batchId)}/videos`, form, onProgress,
    )
  },
  trashBatchFrames: (batchId: string, input: { mode: 'explicit' | 'all_matching'; ids?: string[]; status?: string; search?: string; excluded_ids?: string[]; request_id: string }) =>
    postJson<{ affected_count: number; retention_days: number }>(`/frame-batches/${batchId}/frames/trash`, input),
  listRecycledFrames: (page = 1, pageSize = 30) => getJson<RecycledFramePage>(`/recycle-bin/frames?page=${page}&page_size=${pageSize}`),
  getRecycleBinSummary: () => getJson<RecycleBinSummary>('/recycle-bin/summary'),
  restoreRecycledFrames: (ids: string[]) => postJson<{ affected_count: number }>('/recycle-bin/frames/restore', { ids, request_id: createRequestId() }),
  purgeRecycledFrames: (ids: string[]) => mutateJson<{ deleted_count: number; released_bytes: number }>('DELETE', '/recycle-bin/frames', { ids, request_id: createRequestId(), confirm_count: ids.length }),
  purgeExpiredRecycledFrames: () => postJson<{ deleted_count: number; released_bytes: number }>('/recycle-bin/purge-expired', {}),
  listDatasetReleaseImages: (releaseId: string) => getJson<Array<{ path: string; name: string; size_bytes: number }>>(`/dataset-releases/${releaseId}/images`),
  getDatasetReleaseImageUrl: (releaseId: string, path: string) => `${API_BASE_URL}/dataset-releases/${releaseId}/images/content?path=${encodeURIComponent(path)}`,

  listBatchFrames: (batchId: string, page = 1, pageSize = 60, status?: string, search = '') => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) params.set('status', status)
    if (search) params.set('search', search)
    return getJson<FramePageResponse>(`/frame-batches/${batchId}/frames?${params}`)
  },
  bulkFrameSelection: (batchId: string, input: { selection: { mode: 'explicit' | 'all_matching'; ids?: string[]; status?: string; search?: string; excluded_ids?: string[] }; target_status: string }) =>
    postJson<{ job_id: string; affected_count: number }>(`/frame-batches/${batchId}/bulk-selection`, input),

  getBatchDuplicates: (batchId: string) =>
    getJson<DuplicateGroupSummary[]>(`/frame-batches/${batchId}/duplicates`),

  updateFrameSelection: (batchId: string, selections: Record<string, string>) =>
    postJson<any>(`/frame-batches/${batchId}/selection`, { selections }),

  createAnnotationPackage: (batchId: string) =>
    postJson<{ sha256: string; path: string; download_url: string }>(`/frame-batches/${batchId}/annotation-package`, {}),

  importAnnotations: (taskId: string, archivePath: string, project: string, providerVersion: string) =>
    postJson<{ import_id: string; extracted_root: string; sample_count: number }>('/annotation-imports', {
      task_id: taskId,
      archive_path: archivePath,
      project,
      provider_version: providerVersion,
    }),
  uploadAnnotations: (taskId: string, file: File, project: string, providerVersion: string, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('task_id', taskId)
    form.append('project', project)
    form.append('provider_version', providerVersion)
    form.append('file', file)
    return postFormWithProgress<{ import_id: string; extracted_root: string; sample_count: number }>('/annotation-imports/upload', form, onProgress)
  },

  releaseDataset: (taskId: string, annotationImportId: string, displayName: string, version: string, splitRatios = { train: 70, val: 20, test: 10 }, splitSeed = 42) =>
    postJson<{ release_id: string; release_path: string }>('/dataset-releases', {
      task_id: taskId,
      annotation_import_id: annotationImportId,
      display_name: displayName,
      version,
      split_ratios: splitRatios,
      split_seed: splitSeed,
    }),

  getFrameAssetUrl: (path: string) =>
    `${API_BASE_URL}/frame-assets/content?path=${encodeURIComponent(path)}`,
}
