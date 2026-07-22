# Training Overview and Log Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make training progress, metrics, losses, dataset usage, configuration, and runtime logs understandable from the training details drawer without changing the backend or interrupting active training.

**Architecture:** Extend the existing presentation module with pure functions that normalize sparse epoch telemetry and classify log lines. Keep `TrainingOverviewTab` focused on summary composition, add a self-contained `TrainingLogsTab` for log interactions, and leave artifact downloads in `TrainingArtifactsTab`. All data comes from the existing `TrainingRunDetailsApiResponse`.

**Tech Stack:** React 19, TypeScript 5.8, Ant Design 5, Lucide React, Vitest, Vite.

---

## File Map

- Modify `frontend/src/pages/platform/training/trainingDashboardPresentation.ts`: metric/loss presentation and log filtering pure functions.
- Modify `frontend/src/pages/platform/training/trainingDashboardPresentation.test.ts`: unit tests for sparse metrics, task-specific cards, and log filters.
- Modify `frontend/src/pages/platform/training/TrainingOverviewTab.tsx`: compact progress strip, quality metrics, loss breakdown, dataset guidance, and configuration tags.
- Create `frontend/src/pages/platform/training/TrainingOverviewTab.test.tsx`: server-rendered overview behavior tests.
- Create `frontend/src/pages/platform/training/TrainingLogsTab.tsx`: independent searchable/filterable log workspace.
- Create `frontend/src/pages/platform/training/TrainingLogsTab.test.tsx`: presentation and interaction-independent component tests.
- Modify `frontend/src/pages/platform/training/TrainingArtifactsTab.tsx`: remove inline recent-log body while retaining downloadable log artifact.
- Create `frontend/src/pages/platform/training/TrainingArtifactsTab.test.tsx`: regression test for artifact/log separation.
- Modify `frontend/src/pages/platform/TrainingPage.tsx`: register the runtime-log tab.
- Modify `frontend/src/styles.css`: summary grids, configuration list, log toolbar/viewer, and responsive rules.

### Task 1: Normalize Metrics, Losses, and Logs

**Files:**
- Modify: `frontend/src/pages/platform/training/trainingDashboardPresentation.ts`
- Test: `frontend/src/pages/platform/training/trainingDashboardPresentation.test.ts`

- [ ] **Step 1: Write failing presentation tests**

Add tests proving that the newest finite epoch value is selected, missing values remain absent, detection and segmentation cards differ, and log filtering preserves original line numbers:

```ts
expect(latestFiniteMetric(history, 'map50_mask')).toBe(0.42)
expect(latestFiniteMetric(history, 'missing')).toBeNull()
expect(metricCards('segment', history).map((item) => item.key)).toEqual([
  'map50_mask', 'map50_95_mask', 'map50_box', 'map50_95_box',
])
expect(lossCards('segment', history).map((item) => item.key)).toEqual([
  'train_box_loss', 'train_seg_loss', 'train_cls_loss', 'train_dfl_loss',
])
expect(filterLogLines(lines, { mode: 'diagnostic', level: 'all', query: '' })).toEqual([
  expect.objectContaining({ number: 3, level: 'error' }),
])
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --run src/pages/platform/training/trainingDashboardPresentation.test.ts`

Expected: FAIL because `latestFiniteMetric`, `metricCards`, `lossCards`, and `filterLogLines` do not exist.

- [ ] **Step 3: Implement the pure presentation API**

Add exported types and functions with these signatures:

```ts
export type TrainingMetricCard = { key: string; label: string; value: number | null; help: string }
export type TrainingLossCard = TrainingMetricCard & { trend: LossTrend }
export type TrainingLogLevel = 'info' | 'epoch' | 'warning' | 'error'
export type TrainingLogLine = { number: number; text: string; level: TrainingLogLevel }
export type TrainingLogFilter = { mode: 'live' | 'diagnostic'; level: 'all' | TrainingLogLevel; query: string }

export function latestFiniteMetric(history: TrainingEpochMetrics[], key: string): number | null
export function metricCards(taskType: string, history: TrainingEpochMetrics[]): TrainingMetricCard[]
export function lossCards(taskType: string, history: TrainingEpochMetrics[]): TrainingLossCard[]
export function classifyLogLine(text: string): TrainingLogLevel
export function filterLogLines(lines: string[], filter: TrainingLogFilter): TrainingLogLine[]
```

Use only finite values. Search newest-to-oldest. Detect errors with `traceback|error|exception|failed|fatal|outofmemory|resource_limit`, warnings with `warning|warn|警告`, and epochs with Ultralytics epoch/progress patterns. Diagnostic mode includes only warning/error lines.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `npm test -- --run src/pages/platform/training/trainingDashboardPresentation.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the presentation layer**

```powershell
git add frontend/src/pages/platform/training/trainingDashboardPresentation.ts frontend/src/pages/platform/training/trainingDashboardPresentation.test.ts; git commit -m "feat: add training dashboard presentation model"
```

### Task 2: Rebuild the Real-Time Overview

**Files:**
- Create: `frontend/src/pages/platform/training/TrainingOverviewTab.test.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingOverviewTab.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing overview component tests**

Render a segment run with real epoch metrics and assert that the HTML contains:

```ts
expect(html).toContain('当前阶段')
expect(html).toContain('预计剩余')
expect(html).toContain('Mask mAP50')
expect(html).toContain('Mask Loss')
expect(html).toContain('Class Loss')
expect(html).toContain('用于更新模型参数')
expect(html).toContain('最后 15 轮停止 Mosaic')
expect(html).toContain('类别 A')
```

Add a second case with empty history:

```ts
expect(html).toContain('首轮验证完成后生成')
expect(html).not.toContain('0.0000')
```

- [ ] **Step 2: Run the overview test and verify RED**

Run: `npm test -- --run src/pages/platform/training/TrainingOverviewTab.test.tsx`

Expected: FAIL because the compact labels, metric breakdown, and explanatory copy are absent.

- [ ] **Step 3: Implement the compact overview**

Replace the large circle and bordered `Descriptions` block with:

```tsx
<section className="training-run-strip">...</section>
<section className="training-summary-section" aria-labelledby="training-quality-heading">...</section>
<section className="training-summary-section" aria-labelledby="training-loss-heading">...</section>
<section className="training-dataset-summary">...</section>
<dl className="training-config-summary">...</dl>
<div className="training-class-tags">{classes.map((name) => <Tag key={name}>{name}</Tag>)}</div>
```

Use `metricCards()` and `lossCards()`. Display `首轮验证完成后生成` for missing quality values and `积累至少 2 轮后判断` for unavailable trends. Preserve existing failure, completion, quality, evidence, and warning panels.

- [ ] **Step 4: Add stable responsive styles**

Add grid rules for `.training-run-strip`, `.training-run-stat-grid`, `.training-summary-grid`, `.training-config-summary`, and `.training-class-tags`. Use four columns on wide drawers, two at medium widths, and one at mobile widths. Keep radius at 6px and allow long values/tags to wrap.

- [ ] **Step 5: Run the overview and presentation tests**

Run: `npm test -- --run src/pages/platform/training/TrainingOverviewTab.test.tsx src/pages/platform/training/trainingDashboardPresentation.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the overview**

```powershell
git add frontend/src/pages/platform/training/TrainingOverviewTab.tsx frontend/src/pages/platform/training/TrainingOverviewTab.test.tsx frontend/src/styles.css; git commit -m "feat: clarify real-time training overview"
```

### Task 3: Add the Runtime Log Workspace

**Files:**
- Create: `frontend/src/pages/platform/training/TrainingLogsTab.test.tsx`
- Create: `frontend/src/pages/platform/training/TrainingLogsTab.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing log workspace tests**

Render the component with mixed logs and a `runner_log` artifact. Assert:

```ts
expect(html).toContain('页面展示最近 200 行')
expect(html).toContain('实时日志')
expect(html).toContain('故障诊断')
expect(html).toContain('搜索日志')
expect(html).toContain('下载完整日志')
expect(html).toContain('Traceback')
expect(html).toContain('training-log-line-error')
```

Render without `runner_log` and assert that the full-log download action is absent.

- [ ] **Step 2: Run the log test and verify RED**

Run: `npm test -- --run src/pages/platform/training/TrainingLogsTab.test.tsx`

Expected: FAIL because `TrainingLogsTab` does not exist.

- [ ] **Step 3: Implement `TrainingLogsTab`**

Use local state for mode, level, query, wrapping, and follow mode. Render Ant Design `Segmented`, `Input`, `Select`, `Switch`, and icon buttons. Compute displayed rows with `filterLogLines()`. Keep refs for the scroll viewport and last run id. On log updates, scroll only when follow mode is enabled. Copy `displayed.map(line => line.text).join('\n')`; catch clipboard failures and call `message.error('复制失败，请下载完整日志')`.

Use the existing artifact URL:

```tsx
const fullLog = details.artifacts.find((item) => item.key === 'runner_log')
{fullLog && <Button href={api.getArtifactUrl(fullLog.path)} target="_blank">下载完整日志</Button>}
```

- [ ] **Step 4: Add the fixed log viewport styles**

Add `.training-log-workspace`, `.training-log-toolbar`, `.training-log-viewport`, `.training-log-line`, `.training-log-number`, and level modifier styles. Desktop viewport uses `height: clamp(360px, 55vh, 680px)`; mobile uses `height: 50vh`. `white-space` switches via a `wrap` class without changing container dimensions.

- [ ] **Step 5: Run log tests and verify GREEN**

Run: `npm test -- --run src/pages/platform/training/TrainingLogsTab.test.tsx src/pages/platform/training/trainingDashboardPresentation.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the log workspace**

```powershell
git add frontend/src/pages/platform/training/TrainingLogsTab.tsx frontend/src/pages/platform/training/TrainingLogsTab.test.tsx frontend/src/styles.css; git commit -m "feat: add training runtime log workspace"
```

### Task 4: Integrate Tabs and Separate Artifacts

**Files:**
- Create: `frontend/src/pages/platform/training/TrainingArtifactsTab.test.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingArtifactsTab.tsx`
- Modify: `frontend/src/pages/platform/TrainingPage.tsx`

- [ ] **Step 1: Write the failing artifact separation test**

Render artifacts containing `runner_log` and assert:

```ts
expect(html).toContain('完整运行日志')
expect(html).not.toContain('最近 200 行')
expect(html).not.toContain('Traceback from recent API logs')
```

- [ ] **Step 2: Run the artifact test and verify RED**

Run: `npm test -- --run src/pages/platform/training/TrainingArtifactsTab.test.tsx`

Expected: FAIL because the recent log body still appears in `TrainingArtifactsTab`.

- [ ] **Step 3: Remove the inline log body and add the new tab**

Delete the final `<section>` containing `training-log-detail` from `TrainingArtifactsTab`. Import `TrainingLogsTab` in `TrainingPage.tsx` and insert:

```tsx
{ key: 'logs', label: '运行日志', children: <TrainingLogsTab details={details} /> },
```

between “结果图像” and “参数与产物”.

- [ ] **Step 4: Run focused regression tests**

Run: `npm test -- --run src/pages/platform/training/TrainingArtifactsTab.test.tsx src/pages/platform/training/TrainingLogsTab.test.tsx src/pages/platform/training/TrainingOverviewTab.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit tab integration**

```powershell
git add frontend/src/pages/platform/TrainingPage.tsx frontend/src/pages/platform/training/TrainingArtifactsTab.tsx frontend/src/pages/platform/training/TrainingArtifactsTab.test.tsx; git commit -m "refactor: separate training logs from artifacts"
```

### Task 5: Full Verification and Visual Regression Check

**Files:**
- Verify only; modify earlier files only if a failing test or visual defect requires a focused correction.

- [ ] **Step 1: Run all frontend tests**

Run: `npm test -- --run`

Expected: all tests pass with no unhandled errors.

- [ ] **Step 2: Run the production build**

Run: `npm run build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Inspect current active training without restarting services**

Open `http://127.0.0.1:53257/training`, select the active run, and inspect the overview and logs at desktop and mobile widths. Confirm no overlap, no horizontal page overflow, and an independently scrolling log viewport. Do not stop the API or training process.

- [ ] **Step 4: Check the final diff**

Run: `git diff --check; git status --short; git log -5 --oneline`

Expected: no whitespace errors; only planned files are changed or committed.

- [ ] **Step 5: Commit any verification-only correction**

Only when Step 3 or Step 4 required a correction:

```powershell
git add frontend/src; git commit -m "fix: polish training detail responsiveness"
```
