import { Alert, Button, Descriptions, Popconfirm, Space, Typography } from 'antd'
import { Trash2 } from 'lucide-react'

import type { TrainingResourceCleanupResult } from '../../../api'

const GIB = 1024 ** 3

function formatGib(bytes: number) {
  return `${(bytes / GIB).toFixed(2)} GiB`
}

export async function executeTrainingResourceCleanup(
  cleanup: () => Promise<TrainingResourceCleanupResult>,
  setPending: (pending: boolean) => void,
  setResult: (result: TrainingResourceCleanupResult) => void,
) {
  setPending(true)
  try {
    const result = await cleanup()
    setResult(result)
    return result
  } finally {
    setPending(false)
  }
}

export function TrainingResourceCleanup({
  pending,
  result,
  onCleanup,
}: {
  pending: boolean
  result: TrainingResourceCleanupResult | null
  onCleanup: () => void
}) {
  const snapshot = result?.resource_snapshot ?? {}
  const commit = snapshot.windows_available_commit_bytes
  const physical = snapshot.windows_available_physical_bytes
  const leaspacCount = snapshot.windows_leaspac_process_count
  const leaspacPrivate = snapshot.windows_leaspac_private_bytes
  const cgroupCurrent = snapshot.cgroup_memory_current_bytes
  const cgroupLimit = snapshot.cgroup_memory_limit_bytes
  const resultItems = result ? [
    { key: 'released', label: '已释放磁盘', children: formatGib(result.released_bytes) },
    { key: 'free', label: '当前磁盘可用', children: formatGib(result.disk_free_bytes) },
    { key: 'removed', label: '清理内容', children: `${result.deleted_files} 个文件 / ${result.deleted_directories} 个目录` },
    ...(typeof commit === 'number'
      ? [{ key: 'commit', label: '剩余提交内存', children: formatGib(commit) }]
      : []),
    ...(typeof physical === 'number'
      ? [{ key: 'physical', label: '可用物理内存', children: formatGib(physical) }]
      : []),
    ...(typeof leaspacCount === 'number' && leaspacCount > 0
      ? [{
          key: 'leaspac',
          label: 'LeASPac（未自动结束）',
          children: `${leaspacCount} 个${typeof leaspacPrivate === 'number' ? ` / ${formatGib(leaspacPrivate)}` : ''}`,
        }]
      : []),
    ...(typeof cgroupCurrent === 'number' && typeof cgroupLimit === 'number'
      ? [{ key: 'cgroup', label: '容器内存', children: `${formatGib(cgroupCurrent)} / ${formatGib(cgroupLimit)}` }]
      : []),
  ] : []

  return <section className="training-resource-cleanup" aria-label="训练资源清理">
    <Space direction="vertical" size={6}>
      <Popconfirm
        title="释放平台可安全清理的训练资源？"
        description="仅清理可再生成缓存和过期临时内容，活动训练期间不可执行。"
        okText="确认释放"
        cancelText="取消"
        onConfirm={onCleanup}
        disabled={pending}
      >
        <Button icon={<Trash2 size={16} />} loading={pending}>释放训练资源</Button>
      </Popconfirm>
      <Typography.Text type="secondary">
        数据库、数据集、标注、权重和正式训练结果不会被删除；不会结束系统进程。
      </Typography.Text>
      {result && <Descriptions size="small" column={3} items={resultItems} />}
      {result && result.warnings.length > 0 && <Alert type="warning" showIcon message="部分资源未能清理" description={result.warnings.join('；')} />}
    </Space>
  </section>
}
