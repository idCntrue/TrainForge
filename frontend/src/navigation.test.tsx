import { describe, expect, it } from 'vitest'

import { navigationGroups, navigationLabels } from './navigation'

describe('navigation information architecture', () => {
  it('orders pages by the beginner workflow', () => {
    expect(navigationGroups.map((group) => group.label)).toEqual([
      '数据准备',
      '模型开发',
      '运行管理',
    ])
    expect(navigationGroups.flatMap((group) => group.items.map((item) => item.key))).toEqual([
      'tasks', 'videos', 'review', 'annotation', 'datasets',
      'training', 'models', 'inference',
      'help', 'system',
    ])
  })

  it('uses user-facing names that describe the real page responsibility', () => {
    expect(navigationLabels.dashboard).toBe('工作台')
    expect(navigationLabels.videos).toBe('数据导入')
    expect(navigationLabels.help).toBe('帮助中心')
  })
})
