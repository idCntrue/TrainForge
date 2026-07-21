# Training Metrics Explainability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn existing training telemetry into a professional, beginner-readable metrics dashboard without affecting the active training process.

**Architecture:** Add pure presentation functions beside the existing dashboard helpers, then render their output in focused overview and chart components. All calculations remain in the browser and consume the existing details response.

**Tech Stack:** React 19, TypeScript, Ant Design, Recharts, Vitest, CSS

---

### Task 1: Metric interpretation and health diagnosis

**Files:**
- Modify: `frontend/src/pages/platform/training/trainingDashboardPresentation.test.ts`
- Modify: `frontend/src/pages/platform/training/trainingDashboardPresentation.ts`

- [ ] Write failing tests for newest-value fallback, best epoch, reference bands, short histories, healthy progress, precision/recall imbalance, and multi-signal overfitting risk.
- [ ] Run `npm test -- --run src/pages/platform/training/trainingDashboardPresentation.test.ts` and verify failures identify missing presentation functions.
- [ ] Implement typed pure functions that ignore null/non-finite values and never assign an absolute grade to Loss.
- [ ] Re-run the focused test and verify it passes.

### Task 2: Explainable overview dashboard

**Files:**
- Create: `frontend/src/pages/platform/training/TrainingMetricCard.tsx`
- Create: `frontend/src/pages/platform/training/TrainingHealthPanel.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingOverviewTab.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Write a focused component test proving epoch-history metrics replace a stale null run summary and advisory text is rendered.
- [ ] Run the component test and verify it fails before the components exist.
- [ ] Add compact reusable metric cards and the evidence-based health strip.
- [ ] Replace the two-card KPI area with task-aware quality, loss, and timing information while preserving failures, completion reports, dataset evidence, split distribution, and configuration.
- [ ] Add desktop and mobile styles with stable grid dimensions and no horizontal overflow.
- [ ] Re-run focused presentation and component tests.

### Task 3: Professional chart controls

**Files:**
- Modify: `frontend/src/pages/platform/training/TrainingChartsTab.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Write tests for the recent-20 history selector and best-epoch computation used by the chart header.
- [ ] Verify the tests fail for the missing behavior.
- [ ] Add latest/best header summaries, all/recent-20 segmented control, series toggles, Chinese tooltip labels, and a best-epoch reference line.
- [ ] Re-run focused tests.

### Task 4: Low-impact verification

**Files:**
- Review all modified frontend files.

- [ ] Confirm `git diff --name-only` contains no backend, database, Docker, or training-runner files.
- [ ] Run the focused Vitest files serially.
- [ ] Run TypeScript checking only if current free memory is sufficient; do not run Vite production build while the local training process is active.
- [ ] Inspect the current local API health and verify the active training PID/status is unchanged.
