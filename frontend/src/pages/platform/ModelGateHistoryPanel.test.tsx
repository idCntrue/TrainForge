import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ModelGateRunApiResponse } from '../../api'
import { gateRunDeletionCopy, ModelGateHistoryPanel } from './ModelGateHistoryPanel'

const current: ModelGateRunApiResponse = {
  id: 'run-current', created_at: '2026-07-23T03:00:00Z', status: 'completed_with_warnings', active: true,
  gates: { consistency: true, mask_consistency: false },
  onnx: { path: 'D:\\data\\gate-runs\\run-current\\source.onnx', size_bytes: 41943040, sha256: 'hash', exists: true },
  report_path: 'D:\\data\\gate-runs\\run-current\\result.json', total_size_bytes: 43000000, diagnostics_available: true,
}
const historical: ModelGateRunApiResponse = {
  ...current, id: 'run-old', created_at: '2026-07-22T03:00:00Z', status: 'completed', active: false,
  gates: { consistency: true, mask_consistency: true },
}

describe('ModelGateHistoryPanel', () => {
  it('renders desktop history with active state, warning and file sizes', () => {
    const html = renderToStaticMarkup(<ModelGateHistoryPanel runs={[current, historical]} loading={false} mobile={false} modelStatus="candidate" busy={false} onDelete={() => undefined} />)

    expect(html).toContain('门禁历史')
    expect(html).toContain('当前版本')
    expect(html).toContain('掩膜差异提醒')
    expect(html).toContain('40.0 MB')
    expect(html).toContain('删除此轮及文件')
  })

  it('renders a dedicated mobile record layout', () => {
    const html = renderToStaticMarkup(<ModelGateHistoryPanel runs={[current]} loading={false} mobile modelStatus="candidate" busy={false} onDelete={() => undefined} />)

    expect(html).toContain('gate-history-mobile')
    expect(html).toContain('run-current')
  })

  it('explains every deletion consequence in beginner-friendly language', () => {
    expect(gateRunDeletionCopy(historical, [current, historical], 'candidate').content).toContain('不影响当前模型')
    expect(gateRunDeletionCopy(current, [current, historical], 'candidate').content).toContain('自动切换到上一套门禁')
    expect(gateRunDeletionCopy(current, [current], 'candidate').content).toContain('恢复为“待运行门禁”')
    expect(gateRunDeletionCopy(current, [current], 'published')).toMatchObject({ disabled: true })
    expect(gateRunDeletionCopy(current, [current], 'published').content).toContain('请先归档模型')
  })
})
