# Training Creation Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the long training drawer with a four-step wizard and expose Patience, Optimizer, and Close Mosaic consistently across presets, API requests, uploads, and training details.

**Architecture:** Keep training execution and persistence unchanged. Add focused pure frontend modules for preset/form behavior and wizard presentation, strengthen backend request validation, then compose a dedicated creation drawer component from the existing form fields.

**Tech Stack:** FastAPI, Pydantic, pytest, React 19, TypeScript, Ant Design, Vitest

---

### Task 1: Training Strategy Contract and Backend Validation

**Files:**
- Modify: `src/yolo_factory/api/schemas.py`
- Modify: `tests/integration/test_training_api.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/platform/types.ts`
- Modify: `frontend/src/platform/apiTrainingRepository.ts`
- Modify: `frontend/src/platform/apiTrainingRepository.test.ts`
- Modify: `frontend/src/api.test.ts`

- [ ] **Step 1: Write failing backend validation tests**

Add API tests asserting Optimizer accepts `auto`, `SGD`, `Adam`, and `AdamW`, rejects arbitrary values, and rejects `close_mosaic > epochs` for custom runs. Assert named presets still resolve their authoritative values.

- [ ] **Step 2: Run backend tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/integration/test_training_api.py -q`

Expected: the invalid optimizer and Close Mosaic requests are currently accepted.

- [ ] **Step 3: Implement schema validation**

Use a Pydantic optimizer pattern/normalization that preserves Ultralytics spellings and add a model-level check requiring `close_mosaic <= epochs`. Keep Patience server range backward compatible while the UI constrains new input to `0..300`.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/integration/test_training_api.py -q`

Expected: all training API tests pass.

- [ ] **Step 5: Write failing frontend payload tests**

Assert repository JSON creation forwards `patience`, `optimizer`, `close_mosaic`, and `augment_profile`. Assert custom-weight multipart creation appends the same strategy fields plus serialized augmentation.

- [ ] **Step 6: Run focused frontend tests and verify RED**

Run: `npm test -- --run src/platform/apiTrainingRepository.test.ts src/api.test.ts`

Expected: assertions fail because strategy fields are omitted.

- [ ] **Step 7: Complete frontend types and payload mapping**

Add the fields to `CreateTrainingRunInput`, map response strategy values into `TrainingRun`, forward them through the repository, and append them in `createTrainingRunWithWeight`.

- [ ] **Step 8: Run focused frontend tests and verify GREEN**

Run: `npm test -- --run src/platform/apiTrainingRepository.test.ts src/api.test.ts`

Expected: all focused tests pass.

### Task 2: Preset and Wizard Presentation Logic

**Files:**
- Create: `frontend/src/pages/platform/training/trainingStrategyForm.ts`
- Create: `frontend/src/pages/platform/training/trainingStrategyForm.test.ts`
- Create: `frontend/src/pages/platform/training/trainingCreationWizard.ts`
- Create: `frontend/src/pages/platform/training/trainingCreationWizard.test.ts`
- Modify: `frontend/src/pages/platform/training/trainingFormDefaults.ts`

- [ ] **Step 1: Write failing preset behavior tests**

Test all preset values, CPU detect/segment Batch differences, GPU Batch, GPU preset rejection on CPU, manual strategy/augmentation edits returning `custom`, Patience `0`, and Close Mosaic validation against Epochs.

- [ ] **Step 2: Write failing wizard presentation tests**

Test four ordered steps, fields owned by each step, Back/Next boundaries, confirmation summary, and early-stop explanation text from completed/best epoch and Patience.

- [ ] **Step 3: Run tests and verify RED**

Run: `npm test -- --run src/pages/platform/training/trainingStrategyForm.test.ts src/pages/platform/training/trainingCreationWizard.test.ts`

Expected: fail because both modules do not exist.

- [ ] **Step 4: Implement pure strategy helpers**

Define frontend preset values matching `presets.py`, resource-aware Batch selection, a `strategyPatchForPreset` helper, editable-field detection, and `validateCloseMosaic(epochs, closeMosaic)`.

- [ ] **Step 5: Implement pure wizard helpers**

Define step metadata and field paths, step movement bounds, confirmation rows, and early-stop presentation. Keep these helpers independent of React.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `npm test -- --run src/pages/platform/training/trainingStrategyForm.test.ts src/pages/platform/training/trainingCreationWizard.test.ts`

Expected: all pure logic tests pass.

### Task 3: Four-Step Training Creation Drawer

**Files:**
- Create: `frontend/src/pages/platform/training/TrainingCreationDrawer.tsx`
- Create: `frontend/src/pages/platform/training/TrainingCreationDrawer.test.tsx`
- Modify: `frontend/src/pages/platform/TrainingPage.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write a failing component rendering test**

Use server rendering for stable structural assertions: four step labels, only active-step content, Patience/Optimizer/Close Mosaic on strategy step, confirmation summary, fixed footer commands, and mobile-safe semantic classes.

- [ ] **Step 2: Run the component test and verify RED**

Run: `npm test -- --run src/pages/platform/training/TrainingCreationDrawer.test.tsx`

Expected: fail because the component does not exist.

- [ ] **Step 3: Extract and implement the drawer**

Move existing creation fields into the four steps without removing class aliases, official/custom weights, upload progress, CPU warnings, storage errors, or augmentation controls. Use `Form.validateFields(stepFields)` for Next and full validation for submit.

- [ ] **Step 4: Implement preset/manual-edit behavior**

Selecting a named preset writes strategy and augmentation values. User changes to strategy or augmentation set the preset to `custom`; programmatic preset writes do not. Epoch changes revalidate Close Mosaic.

- [ ] **Step 5: Implement fixed footer and reset behavior**

Back/Next/Join Queue remain visible, closing resets step/form/upload/error state, and the final step summarizes effective values and explains Early Stopping/`best.pt`.

- [ ] **Step 6: Integrate with TrainingPage**

Keep data loading and submission in `TrainingPage` while passing releases/tasks, upload state, storage error, and callbacks into the new component. Ensure regular and custom-weight submissions send identical strategy values.

- [ ] **Step 7: Add responsive styling**

Use a 720px desktop drawer and full-screen mobile drawer. Keep Steps readable at 390px, collapse two-column forms to one column, make body independently scrollable, and reserve safe-area space for the fixed footer.

- [ ] **Step 8: Run focused tests and build**

Run: `npm test -- --run src/pages/platform/training/TrainingCreationDrawer.test.tsx src/pages/platform/training/trainingStrategyForm.test.ts src/pages/platform/training/trainingCreationWizard.test.ts`

Run: `npm run build`

Expected: tests and production build pass.

### Task 4: Training Detail Explanation and Final Verification

**Files:**
- Modify: `frontend/src/pages/platform/training/TrainingArtifactsTab.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingOverviewTab.tsx`
- Modify: `frontend/src/pages/platform/training/trainingDetails.ts`
- Modify: `frontend/src/pages/platform/training/trainingDetails.test.ts`
- Modify: `frontend/src/api.ts`
- Modify: `src/yolo_factory/training/details.py`
- Modify: `tests/unit/training/test_details.py`
- Modify: `docs/current-status.md`

- [ ] **Step 1: Write failing detail-contract tests**

Assert details configuration exposes preset, Patience, Optimizer, Close Mosaic, augmentation profile, requested/completed epochs, best epoch, and stopped-early state. Assert the UI produces the concrete early-stop sentence and falls back for historical runs.

- [ ] **Step 2: Run detail tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/unit/training/test_details.py -q`

Run: `npm test -- --run src/pages/platform/training/trainingDetails.test.ts`

Expected: structured strategy and early-stop fields are missing from the details contract.

- [ ] **Step 3: Extend the read-only detail contract**

Read values from existing run configuration and progress reports; do not add database columns. Add strategy descriptions to the artifact tab and the concrete early-stop explanation to the overview.

- [ ] **Step 4: Run detail tests and verify GREEN**

Run both focused commands from Step 2.

Expected: all focused tests pass.

- [ ] **Step 5: Run complete regression suites**

Run: `$env:PYTHONPATH='src'; python -m pytest -q`

Run: `npm test -- --run`

Run: `npm run build`

Expected: all backend/frontend tests pass and Vite production build succeeds.

- [ ] **Step 6: Perform desktop and mobile visual verification**

Use Playwright at `1440x900` and `390x844`. Verify all four steps, fixed footer, no horizontal overflow, no occluded controls, and readable confirmation summary.

- [ ] **Step 7: Review final diff and data boundaries**

Run: `git diff --check` and `git status --short`. Confirm there are no SQLite migrations, runtime data, model weights, generated screenshots, or deployment-data changes.
