import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from './api'

describe('cascade delete requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends explicit cascade and artifact flags', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    await api.deleteTrainingRun('training-1', true, true)
    await api.deleteModel('model-1', false, true)
    await api.deleteVideoCollection('collection-1', true, true)
    await api.deleteDatasetRelease('release-1', false, true)

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/training-runs/training-1?delete_artifacts=true&cascade=true',
      '/api/model-versions/model-1?delete_artifacts=false&cascade=true',
      '/api/video-collections/collection-1?delete_artifacts=true&cascade=true',
      '/api/dataset-releases/release-1?delete_artifacts=false&cascade=true',
    ])
  })

  it('surfaces FastAPI detail instead of raw JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      text: () => Promise.resolve('{"detail":"delete dependent batches first"}'),
    }))

    await expect(api.deleteVideoCollection('collection-1', false, false)).rejects.toThrow(
      'delete dependent batches first',
    )
  })
})

describe('task requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('creates a task through the same-origin API', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'defects' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.createTask({ id: 'defects', task_type: 'detect', classes: ['scratch'] })

    expect(fetchMock).toHaveBeenCalledWith('/api/tasks', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ id: 'defects', task_type: 'detect', classes: ['scratch'] }),
    }))
  })

  it('shows the FastAPI detail when task creation is rejected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      text: () => Promise.resolve('{"detail":"task id already exists"}'),
    }))

    await expect(api.createTask({ id: 'defects', task_type: 'detect', classes: ['scratch'] })).rejects.toEqual(new Error('task id already exists'))
  })
})

describe('API validation errors', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('formats FastAPI validation details instead of rendering object placeholders', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: () => Promise.resolve(JSON.stringify({
        detail: [
          { loc: ['body', 'epochs'], msg: 'Field required', type: 'missing' },
          { loc: ['body', 'batch'], msg: 'Field required', type: 'missing' },
        ],
      })),
    }))

    await expect(api.createTrainingRun({
      name: 'test',
      task_type: 'segment',
      dataset_release_id: 'dataset-1',
      base_model: 'yolo26s-seg.pt',
      device: 'cpu',
      selected_classes: ['sign'],
      class_aliases: {},
      preset_id: 'cpu-balanced',
    } as never)).rejects.toThrow('epochs：Field required；batch：Field required')
  })

  it('preserves structured training storage details', async () => {
    const detail = {
      code: 'insufficient_training_storage',
      message: '训练至少需要 10 GiB 可用空间',
      free_gib: 7.3,
      free_percent: 18.8,
      required_gib: 10,
      required_percent: 10,
      failed_checks: ['absolute'],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      text: () => Promise.resolve(JSON.stringify({ detail })),
    }))

    const failure = await api.createTrainingRun({} as never).catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.message).toBe(detail.message)
    expect(failure.status).toBe(409)
    expect(failure.detail).toEqual(detail)
  })
})

describe('artifact URLs', () => {
  it('uses the same-origin API for annotation package downloads', () => {
    expect(api.getAnnotationPackageUrl('batch-1')).toBe('/api/annotation-packages/batch-1/download')
  })
})

describe('dataset release requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the user-readable dataset name independently from the version', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ release_id: 'release-1', release_path: 'dataset-releases/release-1' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.releaseDataset(
      'inspection',
      'annotation-1',
      '巡检数据集',
      '1.2.0',
      { train: 70, val: 20, test: 10 },
      42,
    )

    expect(fetchMock).toHaveBeenCalledWith('/api/dataset-releases', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        task_id: 'inspection',
        annotation_import_id: 'annotation-1',
        display_name: '巡检数据集',
        version: '1.2.0',
        split_ratios: { train: 70, val: 20, test: 10 },
        split_seed: 42,
      }),
    }))
  })
})

describe('annotation queue requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('serializes server pagination and status filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ items: [], page: 3, page_size: 30, total: 0, status_counts: {} }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.listAnnotationImages('inspection', 'reviewed', 3, 30)

    expect(fetchMock).toHaveBeenCalledWith('/api/annotation-images?task_id=inspection&status=reviewed&page=3&page_size=30')
    expect(api.getAnnotationThumbnailUrl('frame/1')).toBe('/api/annotation-images/frame%2F1/thumbnail')
  })
})

describe('frame recycle requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('appends browser images to an existing batch as multipart data', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ batch_id: 'batch-1', imported_count: 1, skipped_count: 0 }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['image'], 'new.jpg', { type: 'image/jpeg' })

    await api.appendBatchImages('batch-1', [file])

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/frame-batches/batch-1/images')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.getAll('files')).toEqual([file])
  })

  it('serializes cross-page trash filters and exclusions', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ affected_count: 9, retention_days: 7 }) })
    vi.stubGlobal('fetch', fetchMock)

    await api.trashBatchFrames('batch-1', {
      mode: 'all_matching', status: 'selected', search: 'door', excluded_ids: ['frame-2'], request_id: 'request-1',
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/frame-batches/batch-1/frames/trash', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ mode: 'all_matching', status: 'selected', search: 'door', excluded_ids: ['frame-2'], request_id: 'request-1' }),
    }))
  })

  it('sends restore and confirmed permanent-delete requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ affected_count: 2 }) })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'request-2' })

    await api.restoreRecycledFrames(['frame-1', 'frame-2'])
    await api.purgeRecycledFrames(['frame-1', 'frame-2'])

    expect(fetchMock.mock.calls[0]).toEqual(['/api/recycle-bin/frames/restore', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ ids: ['frame-1', 'frame-2'], request_id: 'request-2' }),
    })])
    expect(fetchMock.mock.calls[1]).toEqual(['/api/recycle-bin/frames', expect.objectContaining({
      method: 'DELETE', body: JSON.stringify({ ids: ['frame-1', 'frame-2'], request_id: 'request-2', confirm_count: 2 }),
    })])
  })
})

describe('video upload requests', () => {
  it('sends selected browser files as multipart form data', async () => {
    class FakeXMLHttpRequest {
      static instance: FakeXMLHttpRequest
      upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
      status = 202
      responseText = JSON.stringify({ job_id: 'job-1', uploaded_count: 1, filenames: ['camera.mp4'] })
      method = ''
      url = ''
      body?: FormData
      onload?: () => void
      onerror?: () => void
      constructor() { FakeXMLHttpRequest.instance = this }
      open(method: string, url: string) { this.method = method; this.url = url }
      send(body: FormData) {
        this.body = body
        this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 })
        this.onload?.()
      }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const file = new File(['video'], 'camera.mp4', { type: 'video/mp4' })
    const onProgress = vi.fn()

    await api.uploadVideos('inspection', 'collection-1', [file], onProgress)

    const request = FakeXMLHttpRequest.instance
    expect(request.method).toBe('POST')
    expect(request.url).toBe('/api/video-collections/upload')
    expect(request.body).toBeInstanceOf(FormData)
    expect(request.body?.get('task_id')).toBe('inspection')
    expect(request.body?.get('collection_id')).toBe('collection-1')
    expect(request.body?.getAll('files')).toEqual([file])
    expect(onProgress).toHaveBeenCalledWith(50)
  })

  it('appends videos and extraction settings to an existing batch', async () => {
    class FakeXMLHttpRequest {
      static instance: FakeXMLHttpRequest
      upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
      status = 202
      responseText = JSON.stringify({ job_id: 'job-append', uploaded_count: 1, filenames: ['more.mp4'] })
      method = ''
      url = ''
      body?: FormData
      onload?: () => void
      onerror?: () => void
      constructor() { FakeXMLHttpRequest.instance = this }
      open(method: string, url: string) { this.method = method; this.url = url }
      send(body: FormData) { this.body = body; this.onload?.() }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const file = new File(['video'], 'more.mp4', { type: 'video/mp4' })

    await api.appendBatchVideos('batch-1', [file], 1.5, 88)

    const request = FakeXMLHttpRequest.instance
    expect(request.method).toBe('POST')
    expect(request.url).toBe('/api/frame-batches/batch-1/videos')
    expect(request.body?.getAll('files')).toEqual([file])
    expect(request.body?.get('interval')).toBe('1.5')
    expect(request.body?.get('quality')).toBe('88')
  })
})

describe('cloud file upload requests', () => {
  afterEach(() => vi.unstubAllGlobals())

  class FakeXMLHttpRequest {
    static instance: FakeXMLHttpRequest
    upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
    status = 201
    responseText = '{}'
    method = ''
    url = ''
    body?: FormData
    onload?: () => void
    onerror?: () => void
    constructor() { FakeXMLHttpRequest.instance = this }
    open(method: string, url: string) { this.method = method; this.url = url }
    send(body: FormData) { this.body = body; this.onload?.() }
  }

  it('uploads an annotation ZIP instead of sending a browser-local path', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const file = new File(['zip'], 'annotations.zip', { type: 'application/zip' })

    await api.uploadAnnotations('lights', file, 'lights-project', '1')

    const request = FakeXMLHttpRequest.instance
    expect(request.url).toBe('/api/annotation-imports/upload')
    expect(request.body?.get('task_id')).toBe('lights')
    expect(request.body?.get('file')).toBe(file)
  })

  it('uploads inference media with its run configuration', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const file = new File(['image'], 'sample.jpg', { type: 'image/jpeg' })

    await api.uploadInferenceRun({ model_version_id: 'model-1', mode: 'image', runtime: 'pt', confidence: 0.25 }, [file])

    const request = FakeXMLHttpRequest.instance
    expect(request.url).toBe('/api/inference-runs/upload')
    expect(request.body?.get('model_version_id')).toBe('model-1')
    expect(request.body?.getAll('files')).toEqual([file])
  })

  it('uploads a custom training weight with its run configuration', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXMLHttpRequest)
    const file = new File(['weights'], 'custom.pt', { type: 'application/octet-stream' })

    await api.createTrainingRunWithWeight({
      name: 'custom', task_type: 'detect', dataset_release_id: 'dataset-1', base_model: '',
      epochs: 10, batch: 2, image_size: 640, device: 'cpu', selected_classes: ['light'], class_aliases: {},
    }, file)

    const request = FakeXMLHttpRequest.instance
    expect(request.url).toBe('/api/training-runs/upload')
    expect(request.body?.get('selected_classes')).toBe('["light"]')
    expect(request.body?.get('base_model_file')).toBe(file)
  })
})
