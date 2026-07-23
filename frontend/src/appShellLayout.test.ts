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

  it('keeps the training wizard form height bounded so the active step can scroll', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')
    expect(css).toContain('.training-creation-drawer .ant-drawer-body > .ant-form { height: 100%; min-height: 0; }')
    expect(css).toContain('.training-wizard-step-content { flex: 1; min-height: 0; overflow-y: auto;')
  })

  it('uses a safe-area-aware fixed mobile navigation instead of a narrow desktop sidebar', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('<MobileBottomNavigation activeView={view} onNavigate={navigate} />')
    expect(css).toContain('--mobile-navigation-height: 68px;')
    expect(css).toContain('.mobile-bottom-navigation { position: fixed;')
    expect(css).toContain('padding-bottom: env(safe-area-inset-bottom);')
    expect(css).toContain('min-height: 44px;')
    expect(css).toContain('.sidebar { display: none; }')
    expect(css).toContain('padding-bottom: calc(var(--mobile-navigation-height) + env(safe-area-inset-bottom) + 18px);')
  })

  it('preserves inference media aspect ratio within minimum and maximum heights', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')
    expect(css).toContain('.inference-result-media { width: 100%; min-height: 240px; max-height: 520px;')
    expect(css).toContain('.inference-result-media img,.inference-result-media video { max-width: 100%; width: auto; min-height: 240px; max-height: 520px; height: auto;')
    expect(css).not.toContain('.inference-result-media { width: 100%; height: clamp(')
  })

  it('browses batch inference results through one preview and a horizontal thumbnail rail', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(css).toContain('.inference-result-viewer { min-width: 0;')
    expect(css).toContain('.inference-result-toolbar { display: flex;')
    expect(css).toContain('flex-wrap: wrap;')
    expect(css).toContain('.inference-thumbnail-rail { display: flex; flex-wrap: nowrap; overflow-x: auto;')
    expect(css).toContain('.inference-thumbnail { position: relative; flex: 0 0 112px; width: 112px; height: 76px;')
    expect(css).toContain('.inference-result-pagination .ant-btn { width: 36px; height: 36px;')
  })

  it('groups inference controls and isolates test-model import from the main workflow', () => {
    const source = fs.readFileSync(path.resolve('src/pages/platform/InferencePage.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('inference-control-section')
    expect(source).toContain('inference-model-picker-row')
    expect(source).toContain('inference-import-modal')
    expect(source).toContain('inference-confidence-value')
    expect(source).toContain('inference-file-summary')
    expect(source).toContain('inference-submit-bar')
    expect(source).toContain('导入新模型')
    expect(css).toContain('.inference-control-section {')
    expect(css).toContain('.inference-model-picker-row { display: grid;')
    expect(css).toContain('.inference-submit-bar {')
  })

  it('provides dataset storage reconciliation diagnostics and explicit repair', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('dataset-reconciliation-trigger')
    expect(source).toContain('dataset-reconciliation-drawer')
    expect(source).toContain('dataset-reconciliation-summary')
    expect(source).toContain('dataset-reconciliation-finding')
    expect(source).toContain('重新注册')
    expect(css).toContain('.dataset-reconciliation-summary { display: grid;')
    expect(css).toContain('.dataset-reconciliation-finding {')
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

  it('provides mobile-native dataset and annotation presentation contracts', () => {
    const source = fs.readFileSync(path.resolve('src/App.tsx'), 'utf8')
    const annotation = fs.readFileSync(path.resolve('src/pages/annotation/AnnotationPage.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('mobile-release-list')
    expect(annotation).toContain('annotation-tool-strip')
    expect(css).toContain('.annotation-tool-strip { overflow-x: auto;')
    expect(css).toContain('min-height: calc(100dvh - 250px);')
    expect(css).toContain('.dataset-image-grid { grid-template-columns: repeat(2, minmax(0, 1fr));')
  })

  it('makes mobile sheets and controls fit the viewport', () => {
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(css).toContain('.mobile-fullscreen-drawer .ant-drawer-body')
    expect(css).toContain('.platform-filterbar .ant-select { width: 100%;')
    expect(css).toContain('.ant-upload-drag { padding-inline: 12px;')
    expect(css).toContain('.inference-result-media { min-height: 180px;')
  })

  it('keeps long model artifact paths inside the model drawer', () => {
    const source = fs.readFileSync(path.resolve('src/pages/platform/ModelsPage.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('model-detail-drawer')
    expect(source).toContain('model-artifact-details')
    expect(source).toContain('model-artifact-path')
    expect(css).toContain('.model-detail-drawer .ant-drawer-body { overflow-x: hidden; }')
    expect(css).toContain('.model-artifact-details { min-width: 0;')
    expect(css).toContain('.model-artifact-path { min-width: 0;')
    expect(css).toContain('.model-artifact-hash { overflow-wrap: anywhere;')
  })

  it('uses a spacious card-based model detail drawer without squeezed gate tables', () => {
    const source = fs.readFileSync(path.resolve('src/pages/platform/ModelsPage.tsx'), 'utf8')
    const css = fs.readFileSync(path.resolve('src/styles.css'), 'utf8')

    expect(source).toContain('model-detail-shell')
    expect(source).toContain('mobile={true}')
    expect(css).toContain('.model-detail-drawer .ant-drawer-body')
    expect(css).toContain('.model-detail-shell { min-width: 0;')
    expect(css).toContain('.model-detail-drawer .ant-drawer-header')
  })
})
