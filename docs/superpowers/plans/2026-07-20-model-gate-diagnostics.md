# Model Gate Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show clear Chinese summaries and expandable sample-level evidence after a model gate run.

**Architecture:** Add a read-only endpoint that safely loads the existing report below the storage root, then keep all human-facing interpretation in a focused frontend presentation module. The model drawer fetches diagnostics on selection and after gate execution, while the existing gate calculations and SQLite schema remain unchanged.

**Tech Stack:** FastAPI, Pydantic, pytest, React 19, TypeScript, Ant Design, Vitest

---

### Task 1: Read-Only Gate Report API

**Files:**
- Modify: `src/yolo_factory/api/schemas.py`
- Modify: `src/yolo_factory/api/app.py`
- Test: `tests/integration/test_model_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests that create a model, write a valid report under the storage root, and assert `GET /api/model-versions/{id}/gate-report` returns `{available: true, report: ...}`. Add cases for no report, a deleted report, malformed JSON, non-object JSON, and a report path outside the storage root. Assert unavailable historical reports return `200` with `available: false`, missing models return `404`, and unsafe or malformed reports return controlled `409` responses without leaking the external path.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/integration/test_model_api.py -q`

Expected: new tests fail because the endpoint does not exist.

- [ ] **Step 3: Add the response schema and endpoint**

Add a schema equivalent to:

```python
class ModelGateReportResponse(BaseModel):
    available: bool
    report: dict | None = None
    reason: str | None = None
```

Add the endpoint before the parameterized model mutation routes. Load the model with `model_repository.get_required`, return unavailable reasons for a null/missing report, validate the resolved path with `relative_to(root)`, parse UTF-8 JSON, require a dictionary, and return controlled HTTP errors for unsafe or invalid reports.

- [ ] **Step 4: Run focused backend tests and verify GREEN**

Run: `python -m pytest tests/integration/test_model_api.py -q`

Expected: all model API tests pass.

### Task 2: Frontend Diagnostic Types and Presentation Logic

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/platform/types.ts`
- Modify: `frontend/src/platform/apiPlatformRepository.ts`
- Create: `frontend/src/pages/platform/modelGateDiagnostics.ts`
- Create: `frontend/src/pages/platform/modelGateDiagnostics.test.ts`

- [ ] **Step 1: Write failing presentation tests**

Cover stable Chinese labels, hard versus advisory classification, total hard-failure count, count mismatch summaries, box/confidence/mask threshold failures, filename extraction from Windows and POSIX paths, quality verdict fallback text, missing-report text, and completion messages for full pass, hard failure, and advisory-only failure.

- [ ] **Step 2: Run the focused frontend test and verify RED**

Run: `npm test -- --run src/pages/platform/modelGateDiagnostics.test.ts`

Expected: fail because `modelGateDiagnostics.ts` does not exist.

- [ ] **Step 3: Add API/report types**

Define typed report structures for sample reports and prediction pairs, add `getModelGateReport(id)` to the API client, extend `ReleaseGate` with `key` and `advisory`, and extend `ModelArtifact` with `gateReportPath` without embedding report contents in list responses.

- [ ] **Step 4: Implement pure presentation helpers**

Implement functions with no React dependency:

```ts
gateDefinition(key)
summarizeGateResult(model, reportResponse)
summarizeConsistency(report)
consistencySampleDetails(sample)
qualityRecommendation(report)
gateCompletionMessage(model)
```

Use thresholds from the existing runner (`box IoU >= 0.80`, `confidence delta <= 0.15`, `mask IoU >= 0.75`) and structured quality verdicts rather than unreliable free-form text.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `npm test -- --run src/pages/platform/modelGateDiagnostics.test.ts`

Expected: all diagnostic presentation tests pass.

### Task 3: Model Drawer Diagnostic Experience

**Files:**
- Modify: `frontend/src/pages/platform/ModelsPage.tsx`
- Create: `frontend/src/pages/platform/ModelGateDiagnosticsPanel.tsx`
- Create: `frontend/src/pages/platform/ModelGateDiagnosticsPanel.test.tsx` only if the current Vitest setup supports DOM rendering; otherwise keep rendering logic covered through pure presentation tests and verify with the production build.
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add a failing behavioral test for state-independent rendering**

Test the panel view-model inputs for: failed rows expanded by default, passed rows compact, advisory badge present, sample filenames shown without absolute paths, and unavailable reports showing the rerun instruction. If DOM tooling is unavailable, add these assertions to the pure panel model builder in `modelGateDiagnostics.test.ts`.

- [ ] **Step 2: Run the test and verify RED**

Run: `npm test -- --run src/pages/platform/modelGateDiagnostics.test.ts`

Expected: fail because the panel model/rendering behavior is missing.

- [ ] **Step 3: Implement the diagnostics panel**

Use Ant Design `Alert`, `Collapse`, and compact stacked records. Render an overall result, Chinese gate rows, a distinct advisory marker, consistency samples with actual/required values, quality recommendations, and report-unavailable fallback. Do not render server absolute paths.

- [ ] **Step 4: Integrate report loading and accurate completion feedback**

In `ModelsPage`, fetch diagnostics when a model is selected, clear stale diagnostics when selection changes, reload after `runModelGates`, keep diagnostic load errors separate from model loading, and replace the unconditional success toast with `gateCompletionMessage(mapModel(response))` using warning feedback when hard gates fail.

- [ ] **Step 5: Add responsive styles**

Keep the desktop hierarchy compact and render samples as full-width stacked records under the existing mobile breakpoint. Ensure the drawer actions and diagnostic text wrap without horizontal overflow.

- [ ] **Step 6: Run frontend tests and build**

Run: `npm test -- --run`

Run: `npm run build`

Expected: all tests pass and TypeScript/Vite build succeeds.

### Task 4: Regression Verification and Documentation

**Files:**
- Modify: `docs/current-status.md`

- [ ] **Step 1: Document the user-visible behavior**

Record the read-only report endpoint, hard/advisory distinction, sample-level diagnostics, and the fact that no database migration is involved.

- [ ] **Step 2: Run backend regression tests**

Run: `python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend regression tests and build again**

Run: `npm test -- --run && npm run build` in a shell that supports `&&`, or execute the two commands separately in Windows PowerShell 5.

Expected: all frontend tests pass and the build completes.

- [ ] **Step 4: Review the final diff**

Run: `git diff --check`

Run: `git status --short`

Confirm the implementation does not alter gate thresholds, migrations, deployment data exclusions, SQLite files, model weights, or runtime data.
