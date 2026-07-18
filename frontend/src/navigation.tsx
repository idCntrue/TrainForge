import type { ReactNode } from 'react'
import type { MenuProps } from 'antd'
import { BookOpen, Box, Boxes, Database, FlaskConical, FolderArchive, Gauge, PencilRuler, ScanSearch, Server, Upload } from 'lucide-react'

export type ViewKey = 'dashboard' | 'tasks' | 'videos' | 'review' | 'annotation' | 'datasets' | 'training' | 'models' | 'inference' | 'help' | 'system'

const viewKeys: ViewKey[] = ['dashboard', 'tasks', 'videos', 'review', 'annotation', 'datasets', 'training', 'models', 'inference', 'help', 'system']

export function pathForView(view: ViewKey): string {
  return `/${view}`
}

export function viewFromPath(pathname: string): ViewKey {
  const segment = pathname.split('/').filter(Boolean)[0]
  return viewKeys.includes(segment as ViewKey) ? segment as ViewKey : 'dashboard'
}

export interface NavigationItem {
  key: ViewKey
  label: string
  icon: ReactNode
}

export const navigationLabels: Record<ViewKey, string> = {
  dashboard: '工作台',
  tasks: '任务管理',
  videos: '数据导入',
  review: '数据筛选',
  annotation: '原生标注',
  datasets: '数据集版本',
  training: '训练运行',
  models: '模型中心',
  inference: '推理工作台',
  help: '帮助中心',
  system: '系统状态',
}

const item = (key: ViewKey, icon: ReactNode): NavigationItem => ({ key, label: navigationLabels[key], icon })

export const dashboardNavigationItem = item('dashboard', <Gauge size={18} />)

export const navigationGroups = [
  {
    key: 'data-preparation',
    label: '数据准备',
    items: [
      item('tasks', <Boxes size={18} />),
      item('videos', <Upload size={18} />),
      item('review', <FolderArchive size={18} />),
      item('annotation', <PencilRuler size={18} />),
      item('datasets', <Database size={18} />),
    ],
  },
  {
    key: 'model-development',
    label: '模型开发',
    items: [
      item('training', <FlaskConical size={18} />),
      item('models', <Box size={18} />),
      item('inference', <ScanSearch size={18} />),
    ],
  },
  {
    key: 'operations',
    label: '运行管理',
    items: [
      item('help', <BookOpen size={18} />),
      item('system', <Server size={18} />),
    ],
  },
]

export const navigationMenuItems: MenuProps['items'] = [
  { ...dashboardNavigationItem },
  ...navigationGroups.map((group) => ({
    key: group.key,
    type: 'group' as const,
    label: group.label,
    children: group.items.map((navigationItem) => ({ ...navigationItem })),
  })),
]
