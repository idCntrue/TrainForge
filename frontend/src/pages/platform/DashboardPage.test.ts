import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('dashboard status claims', () => {
  const source = fs.readFileSync(path.resolve('src/pages/platform/DashboardPage.tsx'), 'utf8')

  it('does not claim health without health data', () => {
    expect(source).not.toContain('服务正常')
  })

  it('describes absent active runs without claiming resources are idle', () => {
    expect(source).not.toContain('计算资源空闲')
    expect(source).not.toContain('计算资源处于空闲状态')
    expect(source).toContain('当前无进行中的训练运行')
  })
})
