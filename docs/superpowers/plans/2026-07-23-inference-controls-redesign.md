# Inference Controls Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tall, undifferentiated inference form with grouped configuration sections and an isolated imported-model modal.

**Architecture:** `InferencePage` continues to own inference state and API calls. A second Ant Design form owns import-only fields inside a modal, preventing import drafts from participating in inference validation; CSS provides the grouped visual hierarchy and responsive collapse.

**Tech Stack:** React 19, TypeScript 5.8, Ant Design 5, Lucide React, Vitest, CSS.

---

### Task 1: Define the interaction contract

**Files:**
- Modify: `frontend/src/appShellLayout.test.ts`

- [ ] Add a failing source/CSS contract test asserting `inference-control-section`, `inference-model-picker-row`, `inference-import-modal`, `inference-confidence-value`, `inference-file-summary`, and `inference-submit-bar` exist.
- [ ] Run `npm test -- --run src/appShellLayout.test.ts` and confirm it fails because the new selectors are absent.

### Task 2: Restructure the inference controls

**Files:**
- Modify: `frontend/src/pages/platform/InferencePage.tsx`

- [ ] Add `importOpen`, a separate `importForm`, and `Form.useWatch('confidence', form)` state.
- [ ] Change `importModel` to validate the import form, retain the selected file after errors, and close/reset the modal after success.
- [ ] Group the main form into model, runtime, media, and threshold sections with compact headings.
- [ ] Replace the inline import form with an existing-model row and an `Import new model` button that opens the modal.
- [ ] Add selected-file count, current confidence value, concise threshold guidance, and a dedicated submit bar.
- [ ] Run `npm test -- --run src/appShellLayout.test.ts` and confirm the source assertions pass while CSS assertions still fail.

### Task 3: Implement responsive visual hierarchy

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appShellLayout.test.ts`

- [ ] Add compact section surfaces, a two-column model field grid, compact test notice, aligned model picker action, bounded upload drop zone, confidence header, and stable submit bar.
- [ ] Add mobile rules that collapse field grids and model picker rows to one column while preserving 44px actions.
- [ ] Run `npm test -- --run src/appShellLayout.test.ts src/pages/platform/InferenceResultViewer.test.tsx` and confirm both files pass.
- [ ] Run `npm test -- --run` and `npm run build` and confirm the complete frontend suite and production build pass.
- [ ] Run `git diff --check`, inspect the diff, and commit the implementation.
