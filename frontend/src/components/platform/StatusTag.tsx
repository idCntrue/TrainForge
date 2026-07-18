import { Tag } from 'antd'
import { statusLabel } from './statusPresentation'

const colors: Record<string, string> = {
  queued: 'gold', running: 'processing', evaluating: 'processing', exporting: 'cyan', verifying: 'blue',
  completed: 'success', published: 'success', passed: 'success', failed: 'error', blocked: 'error', cancelled: 'default', candidate: 'blue', interrupted: 'warning',
}

export function StatusTag({ status }: { status: string }) {
  return <Tag color={colors[status] ?? 'default'}>{statusLabel(status)}</Tag>
}
