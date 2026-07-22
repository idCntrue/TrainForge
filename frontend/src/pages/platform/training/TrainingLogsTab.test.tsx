import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { TrainingRunDetailsApiResponse } from '../../../api'
import { TrainingLogsTab } from './TrainingLogsTab'

const details = {
  run_id: 'run-1',
  logs: ['Ultralytics training started', 'Epoch 3/200 GPU_mem 7.2G', 'WARNING worker count is low', 'Traceback: CUDA out of memory'],
  artifacts: [{ key: 'runner_log', name: 'runner.log', kind: 'file', path: '/runs/run-1/runner.log', size_bytes: 1024 }],
} as TrainingRunDetailsApiResponse

describe('TrainingLogsTab', () => {
  it('shows log controls, classified lines, and the complete log download', () => {
    const html = renderToStaticMarkup(<TrainingLogsTab details={details} />)
    expect(html).toContain('页面展示最近 200 行')
    expect(html).toContain('实时日志')
    expect(html).toContain('故障诊断')
    expect(html).toContain('搜索日志')
    expect(html).toContain('下载完整日志')
    expect(html).toContain('training-full-log-download')
    expect(html).toContain('Traceback')
    expect(html).toContain('training-log-line-error')
  })

  it('does not show a broken full-log action when no runner log artifact exists', () => {
    const html = renderToStaticMarkup(<TrainingLogsTab details={{ ...details, artifacts: [] }} />)
    expect(html).not.toContain('training-full-log-download')
  })
})
