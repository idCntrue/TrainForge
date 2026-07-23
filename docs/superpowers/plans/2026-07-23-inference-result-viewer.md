# Inference Result Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace vertically stacked batch inference results with one active preview, previous/next navigation, and a horizontally scrolling annotated-result thumbnail rail.

**Architecture:** Keep inference lifecycle state in `InferencePage` and move completed-result presentation into a focused `InferenceResultViewer`. Put index boundary rules in pure presentation helpers so they can be tested without a DOM, while the component owns keyboard, swipe, and thumbnail-scroll behavior.

**Tech Stack:** React 19, TypeScript 5.8, Ant Design 5, Lucide React, Vitest, CSS.

---

### Task 1: Result navigation contract

**Files:**
- Modify: `frontend/src/pages/platform/inferencePresentation.ts`
- Modify: `frontend/src/pages/platform/inferencePresentation.test.ts`

- [ ] **Step 1: Write failing navigation tests**

Add tests for `clampInferenceResultIndex(index, resultCount)` and `canNavigateInferenceResults(mode, resultCount)`. Cover negative indexes, an index beyond the final item, an empty collection, batch mode with multiple items, and single-image/video modes.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `npm test -- --run src/pages/platform/inferencePresentation.test.ts`

Expected: FAIL because the two helper exports do not exist.

- [ ] **Step 3: Implement the pure helpers**

Add:

```ts
export function clampInferenceResultIndex(index: number, resultCount: number) {
  if (resultCount <= 0) return 0
  return Math.min(Math.max(index, 0), resultCount - 1)
}

export function canNavigateInferenceResults(mode: InferenceMode, resultCount: number) {
  return mode === 'batch' && resultCount > 1
}
```

- [ ] **Step 4: Run the focused test and verify pass**

Run: `npm test -- --run src/pages/platform/inferencePresentation.test.ts`

Expected: all tests in the file PASS.

- [ ] **Step 5: Commit the navigation contract**

```powershell
git add frontend/src/pages/platform/inferencePresentation.ts frontend/src/pages/platform/inferencePresentation.test.ts; git commit -m "test: define inference result navigation"
```

### Task 2: Controlled inference result viewer

**Files:**
- Create: `frontend/src/pages/platform/InferenceResultViewer.tsx`
- Create: `frontend/src/pages/platform/InferenceResultViewer.test.tsx`
- Modify: `frontend/src/pages/platform/InferencePage.tsx`

- [ ] **Step 1: Write failing static component tests**

Render the component with `renderToStaticMarkup` and representative image, batch, and video runs. Assert that a batch run exposes the current counter, previous/next labels, annotated thumbnail rail, active thumbnail state, active result metadata, and artifact action; assert that single-image and video runs do not render the thumbnail rail or image navigation.

- [ ] **Step 2: Run the component test and verify failure**

Run: `npm test -- --run src/pages/platform/InferenceResultViewer.test.tsx`

Expected: FAIL because `InferenceResultViewer` does not exist.

- [ ] **Step 3: Implement the focused component**

Create props that accept the completed `InferenceRun`, `showStructuredMasks`, and `onStructuredMasksChange`. Use local `activeIndex`, reset it when `run.id` changes, clamp it when result count changes, and derive one active result. Implement icon-only previous/next buttons with tooltips and Chinese accessible labels, a focusable viewer with ArrowLeft/ArrowRight handling, touch start/end handlers with a 48px horizontal threshold, and thumbnail refs that call `scrollIntoView({ block: 'nearest', inline: 'nearest' })` when selection changes.

Render only the active full-size image/video. For batch images, render annotated artifact thumbnails with lazy loading, an ordinal, `aria-current`, tooltip filename, and a click handler. Keep structured polygon overlay logic scoped to the active result. Put current-result filename, summary, duration, counter, and artifact action in the active-result toolbar.

- [ ] **Step 4: Replace the completed-result List in `InferencePage`**

Keep queued, running, empty, error, status, and cancellation behavior in `InferencePage`. Replace only the completed `List` branch with:

```tsx
<InferenceResultViewer
  run={run}
  showStructuredMasks={showStructuredMasks}
  onStructuredMasksChange={setShowStructuredMasks}
/>
```

Move the structured-mask switch from the page heading into the viewer toolbar, remove imports used only by the old result list, and preserve video behavior.

- [ ] **Step 5: Run component and presentation tests**

Run: `npm test -- --run src/pages/platform/InferenceResultViewer.test.tsx src/pages/platform/inferencePresentation.test.ts`

Expected: all focused tests PASS.

- [ ] **Step 6: Commit the viewer component**

```powershell
git add frontend/src/pages/platform/InferenceResultViewer.tsx frontend/src/pages/platform/InferenceResultViewer.test.tsx frontend/src/pages/platform/InferencePage.tsx; git commit -m "feat: add inference result viewer"
```

### Task 3: Responsive viewer layout and verification

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appShellLayout.test.ts`

- [ ] **Step 1: Write failing CSS contract assertions**

Assert that `.inference-thumbnail-rail` is a non-wrapping horizontal flex container with `overflow-x: auto`, `.inference-thumbnail` has stable dimensions, `.inference-result-toolbar` supports wrapping, and mobile rules keep thumbnail navigation horizontal with stable touch targets.

- [ ] **Step 2: Run the layout test and verify failure**

Run: `npm test -- --run src/appShellLayout.test.ts`

Expected: FAIL because the new viewer selectors are absent.

- [ ] **Step 3: Implement desktop and mobile styles**

Remove obsolete vertical-list layout rules. Add a bounded media stage, compact active-result toolbar, stable 36px navigation buttons, a horizontal thumbnail rail, selected/focus thumbnail styling, filename truncation, and mobile wrapping. Keep image/video aspect-ratio preservation and ensure the rail cannot create page-level horizontal overflow.

- [ ] **Step 4: Run focused tests**

Run: `npm test -- --run src/pages/platform/InferenceResultViewer.test.tsx src/pages/platform/inferencePresentation.test.ts src/appShellLayout.test.ts`

Expected: all focused tests PASS.

- [ ] **Step 5: Run full frontend tests and production build**

Run: `npm test -- --run`

Expected: all frontend tests PASS.

Run: `npm run build`

Expected: TypeScript and Vite production build complete successfully.

- [ ] **Step 6: Inspect the final diff and commit layout changes**

Run: `git diff --check; git status --short`

Expected: no whitespace errors and only intended files are modified.

```powershell
git add frontend/src/styles.css frontend/src/appShellLayout.test.ts; git commit -m "style: refine batch inference browsing"
```
