import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { TrainingResourceCleanupResult } from '../../../api'
import { executeTrainingResourceCleanup, TrainingResourceCleanup } from './TrainingResourceCleanup'

const baseResult: TrainingResourceCleanupResult = {
  released_bytes: 2 * 1024 ** 3,
  deleted_files: 3,
  deleted_directories: 1,
  skipped_symlinks: 0,
  python_collected_objects: 7,
  cuda_cache_cleared: false,
  disk_free_bytes: 20 * 1024 ** 3,
  disk_total_bytes: 40 * 1024 ** 3,
  resource_snapshot: {},
  warnings: [],
}

describe('TrainingResourceCleanup', () => {
  it('states the protected data boundary before cleanup', () => {
    const html = renderToStaticMarkup(<TrainingResourceCleanup pending={false} result={null} onCleanup={vi.fn()} />)

    expect(html).toContain('释放训练资源')
    expect(html).toContain('数据库、数据集、标注、权重和正式训练结果不会被删除')
    expect(html).toContain('不会结束系统进程')
  })

  it('renders Windows memory and external process evidence', () => {
    const html = renderToStaticMarkup(<TrainingResourceCleanup pending={false} onCleanup={vi.fn()} result={{
      ...baseResult,
      resource_snapshot: {
        windows_available_commit_bytes: 9 * 1024 ** 3,
        windows_available_physical_bytes: 5.5 * 1024 ** 3,
        windows_leaspac_process_count: 30,
        windows_leaspac_private_bytes: 31 * 1024 ** 3,
      },
    }} />)

    expect(html).toContain('已释放磁盘')
    expect(html).toContain('2.00 GiB')
    expect(html).toContain('剩余提交内存')
    expect(html).toContain('9.00 GiB')
    expect(html).toContain('可用物理内存')
    expect(html).toContain('5.50 GiB')
    expect(html).toContain('30 个 / 31.00 GiB')
    expect(html).toContain('未自动结束')
  })

  it('renders Linux cgroup memory without Windows-only rows', () => {
    const html = renderToStaticMarkup(<TrainingResourceCleanup pending={false} onCleanup={vi.fn()} result={{
      ...baseResult,
      resource_snapshot: {
        cgroup_memory_current_bytes: 3 * 1024 ** 3,
        cgroup_memory_limit_bytes: 10 * 1024 ** 3,
      },
    }} />)

    expect(html).toContain('容器内存')
    expect(html).toContain('3.00 GiB / 10.00 GiB')
    expect(html).not.toContain('剩余提交内存')
    expect(html).not.toContain('LeASPac')
  })

  it('sets pending around one request and only stores successful results', async () => {
    const pending: boolean[] = []
    const stored: TrainingResourceCleanupResult[] = []
    const cleanup = vi.fn().mockResolvedValue(baseResult)

    await executeTrainingResourceCleanup(cleanup, (value) => pending.push(value), (value) => stored.push(value))

    expect(cleanup).toHaveBeenCalledTimes(1)
    expect(pending).toEqual([true, false])
    expect(stored).toEqual([baseResult])

    const failedPending: boolean[] = []
    const failedStored: TrainingResourceCleanupResult[] = []
    await expect(executeTrainingResourceCleanup(
      vi.fn().mockRejectedValue(new Error('active training')),
      (value) => failedPending.push(value),
      (value) => failedStored.push(value),
    )).rejects.toThrow('active training')
    expect(failedPending).toEqual([true, false])
    expect(failedStored).toEqual([])
  })
})
