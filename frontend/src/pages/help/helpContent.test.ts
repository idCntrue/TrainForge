import { describe, expect, it } from 'vitest'

import { helpChapters, searchHelp } from './helpContent'

describe('offline help content', () => {
  it('covers the full product manual structure', () => {
    expect(helpChapters.map((chapter) => chapter.id)).toEqual([
      'quick-start', 'workflow', 'native-annotation', 'pages', 'models', 'data', 'troubleshooting', 'deployment', 'training-quality', 'glossary',
    ])
  })

  it.each(['原生标注', '修改类别', 'SAM2', '追加图片', '审核通过'])(
    'documents native annotation topic: %s',
    (keyword) => {
      expect(searchHelp(keyword).map((chapter) => chapter.id)).toContain('native-annotation')
    },
  )

  it.each(['安全重试', '独立测试', '证据不足'])('documents training quality topic: %s', (keyword) => {
    expect(searchHelp(keyword).map((chapter) => chapter.id)).toContain('training-quality')
  })

  it('searches titles, summaries and section content', () => {
    expect(searchHelp('删除失败').map((chapter) => chapter.id)).toContain('troubleshooting')
    expect(searchHelp('视频抽帧').map((chapter) => chapter.id)).toContain('workflow')
    expect(searchHelp('云端部署').map((chapter) => chapter.id)).toContain('deployment')
    expect(searchHelp('中文显示名称').map((chapter) => chapter.id)).toContain('pages')
  })

  it.each([
    'Docker Compose',
    'NVIDIA Container Toolkit',
    '数据迁移',
    'dry-run',
    '备份恢复',
    '单实例',
    '无 GPU',
    '浏览器上传',
    'CI/CD',
    'DEPLOY_SSH_KEY',
  ])('documents cloud operation topic: %s', (keyword) => {
    expect(searchHelp(keyword).map((chapter) => chapter.id)).toContain('deployment')
  })

  it.each([
    'CPU 安全模式',
    'API_MEMORY_LIMIT',
    '8 GiB',
    'update-from-package.sh',
  ])('documents bounded training and safe update topic: %s', (keyword) => {
    expect(searchHelp(keyword).map((chapter) => chapter.id)).toContain('deployment')
  })
})
