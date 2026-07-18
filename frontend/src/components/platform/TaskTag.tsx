import { Tag } from 'antd'
import type { TaskType } from '../../platform/types'

const colors: Record<TaskType, string> = { detect: 'green', segment: 'cyan', classify: 'blue', pose: 'purple', obb: 'orange' }

export function TaskTag({ task }: { task: TaskType }) {
  return <Tag color={colors[task]}>{task.toUpperCase()}</Tag>
}
