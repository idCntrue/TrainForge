import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('existing batch video append workflow', () => {
  it('exposes upload, extraction settings and candidate-state guidance', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')

    expect(source).toContain('追加视频抽帧')
    expect(source).toContain('抽帧间隔（秒）')
    expect(source).toContain('JPEG 质量')
    expect(source).toContain('新抽取图片默认进入待筛选状态')
    expect(source).toContain('api.appendBatchVideos')
  })
})
