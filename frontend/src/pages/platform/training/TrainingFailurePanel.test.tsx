import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { TrainingFailurePanel } from './TrainingFailurePanel'

describe('TrainingFailurePanel', () => {
  it('shows actionable summary and never fabricates a metric', () => {
    const html = renderToStaticMarkup(<TrainingFailurePanel
      diagnostic={{
        schema_version: 1, code: 'resource_limit', summary: '训练进程被外部强制终止',
        action: '使用安全配置重试', technical_message: 'exit 137', exception_type: null,
        traceback: null, exit_code: 137, failure_phase: 'training', failure_scope: 'training',
        last_successful_epoch: 78, total_epochs: 100, occurred_at: '2026-07-16',
        evidence: ['SIGKILL'], resource_snapshot: {}, recoverability: null,
      }}
      recovery={{ can_safe_retry: true, can_evaluate_best: false, best_weight_path: null, preserved_artifact_count: 4, reason: '需要重试' }}
      latestMetric={undefined}
      logs={[]}
      pending={false}
      onSafeRetry={vi.fn()}
      onEvaluateBest={vi.fn()}
    />)

    expect(html).toContain('第 78/100 轮后失败')
    expect(html).toContain('使用安全配置重试')
    expect(html).toContain('--')
    expect(html).not.toContain('评估已有最佳权重</button>')
  })

  it('shows Windows commit memory and LeASPac evidence when available', () => {
    const html = renderToStaticMarkup(<TrainingFailurePanel
      diagnostic={{
        schema_version: 1, code: 'resource_limit', summary: 'Windows 内存压力导致训练停止',
        action: '释放提交内存后重试', technical_message: 'exit 0xC0000005', exception_type: null,
        traceback: null, exit_code: 3221225477, failure_phase: 'training', failure_scope: 'training',
        last_successful_epoch: 63, total_epochs: 100, occurred_at: '2026-07-22',
        evidence: ['0xC0000005'], resource_snapshot: {
          windows_available_commit_bytes: 6 * 1024 ** 3,
          windows_available_physical_bytes: 3.5 * 1024 ** 3,
          windows_leaspac_process_count: 30,
          windows_leaspac_private_bytes: 31 * 1024 ** 3,
        }, recoverability: null,
      }}
      recovery={null}
      logs={[]}
      pending={false}
      onSafeRetry={vi.fn()}
      onEvaluateBest={vi.fn()}
    />)

    expect(html).toContain('剩余提交内存')
    expect(html).toContain('6.00 GiB')
    expect(html).toContain('可用物理内存')
    expect(html).toContain('3.50 GiB')
    expect(html).toContain('LeASPac')
    expect(html).toContain('30 个 / 31.00 GiB')
  })

  it('explains historical TrainingMemoryPressure diagnostics classified as runner failures', () => {
    const html = renderToStaticMarkup(<TrainingFailurePanel
      diagnostic={{
        schema_version: 1, code: 'runner_failed', summary: '训练进程异常退出',
        action: '查看技术诊断和日志', technical_message: '剩余提交内存 9.35 GiB，可用物理内存 2.91 GiB',
        exception_type: 'TrainingMemoryPressure', traceback: null, exit_code: 1,
        failure_phase: 'preparing', failure_scope: 'training', last_successful_epoch: null,
        total_epochs: null, occurred_at: '2026-07-22', evidence: [], resource_snapshot: {}, recoverability: null,
      }}
      recovery={null}
      logs={[]}
      pending={false}
      onSafeRetry={vi.fn()}
      onEvaluateBest={vi.fn()}
    />)

    expect(html).toContain('Windows 内存门禁已安全停止训练')
    expect(html).toContain('释放物理内存后再重试')
    expect(html).not.toContain('训练进程异常退出')
  })
})
