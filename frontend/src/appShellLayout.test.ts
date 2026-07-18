import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

describe('application shell layout', () => {
  it('uses the public TrainForge brand in the application shell', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const dashboard = fs.readFileSync(path.resolve('src/pages/platform/DashboardPage.tsx'), 'utf8')

    expect(source).toContain('<div className="brand-mark">TF</div>')
    expect(source).toContain('<strong>TrainForge</strong>')
    expect(source).not.toContain('<strong>YOLO Factory</strong>')
    expect(dashboard).toContain('<strong>TRAINFORGE CONTROL</strong>')
  })

  it('exposes the AGPL source repository to network users', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')

    expect(source).toContain('AGPL-3.0')
    expect(source).toContain('https://github.com/idCntrue/TrainForge')
  })

  it('keeps the browser root fixed and scrolls only the content region', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')
    expect(css).toContain('html, body, #root { height: 100%; overflow: hidden; }')
    expect(css).toContain('.app-shell { height: 100vh; overflow: hidden;')
    expect(css).toContain('.content { flex: 1; min-height: 0;')
  })

  it('preserves inference media aspect ratio within minimum and maximum heights', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')
    expect(css).toContain('.inference-result-media { width: 100%; min-height: 240px; max-height: 520px;')
    expect(css).toContain('.inference-result-media img,.inference-result-media video { max-width: 100%; width: auto; min-height: 240px; max-height: 520px; height: auto;')
    expect(css).not.toContain('.inference-result-media { width: 100%; height: clamp(')
  })

  it('separates batch metrics, primary review actions, and destructive batch controls', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('review-batch-summary')
    expect(source).toContain('review-batch-metrics')
    expect(source).toContain('review-primary-actions')
    expect(source).toContain('review-batch-danger-actions')
    expect(css).toContain('.review-batch-summary')
    expect(css).toContain('.review-batch-metrics')
  })

  it('uses task contract cards instead of a wide task definition table', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('task-contract-list')
    expect(source).toContain('task-contract-card')
    expect(source).toContain('task-contract-classes')
    expect(css).toContain('.task-contract-list')
    expect(css).toContain('.task-contract-card')
  })

  it('uses import batch cards instead of a wide collection table', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('import-batch-list')
    expect(source).toContain('import-batch-card')
    expect(source).toContain('import-batch-actions')
    expect(css).toContain('.import-batch-list')
    expect(css).toContain('.import-batch-card')
  })
})
