import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('annotation inspector narrow layout', () => {
  it('prevents the 260px inspector from gaining a horizontal scrollbar', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(css).toContain('.annotation-properties { overflow-y: auto; overflow-x: hidden;')
    expect(css).toContain('.smart-select-actions { padding-top: 8px; display: grid; grid-template-columns: 1fr; gap: 8px;')
    expect(css).toContain('.smart-select-actions .ant-btn { width: 100%; min-width: 0; }')
  })
})
