# Model Gate Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve existing ONNX artifacts during gate runs and make segmentation mask-only differences advisory rather than publication-blocking.

**Architecture:** The executor already creates a unique attempt directory, so the runner will export from an attempt-local PT copy and retain the resulting ONNX there. Comparison output will separate hard detection compatibility from mask fidelity, while repository hard-gate state continues to use `consistency` and exposes `mask_consistency` as advisory.

**Tech Stack:** Python 3.10, Ultralytics, NumPy/OpenCV, FastAPI, pytest, SQLite repository.

---

### Task 1: Separate hard consistency from mask fidelity

**Files:**
- Modify: `src/yolo_factory/models/gate_runner.py`
- Test: `tests/unit/models/test_gate_runner.py`

- [ ] **Step 1: Write failing comparison tests**

Add tests asserting that equal class/count with passing box IoU and confidence remains hard-compatible when mask IoU is below `0.75`, while count or box mismatch remains blocking. Assert the pair contains `mask_passed=False` and the sample contains `mask_consistency=False`.

- [ ] **Step 2: Verify RED**

Run: `$env:PYTHONPATH="$PWD\src"; python -m pytest tests/unit/models/test_gate_runner.py -q`

Expected: FAIL because comparison output does not separate hard and mask results.

- [ ] **Step 3: Implement comparison policy**

Keep class/count, box IoU `0.80`, and confidence delta `0.15` in `pair["passed"]`. Store mask threshold result separately in `pair["mask_passed"]`; return both `passed` and `mask_consistency` at sample level.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 test command and expect all tests to pass.

### Task 2: Isolate ONNX export per gate attempt

**Files:**
- Modify: `src/yolo_factory/models/gate_runner.py`
- Test: `tests/unit/models/test_gate_runner.py`

- [ ] **Step 1: Write failing export-isolation test**

Test an export helper with a fake model loader/exporter. Assert it copies the PT into `<attempt>/exported/source.pt`, exports beside that copy, returns `<attempt>/exported/source.onnx`, removes the PT copy, and leaves an existing source-directory ONNX byte-for-byte unchanged.

- [ ] **Step 2: Verify RED**

Run the Task 1 test command and expect failure because the helper does not exist.

- [ ] **Step 3: Implement isolated export helper**

Create the attempt-local export directory, copy the PT, instantiate YOLO from the copy, export with the existing fixed settings, resolve the result, and remove the copied PT in `finally`. Reject an export path outside the attempt directory.

- [ ] **Step 4: Use isolated artifact in gate run**

Load the original PT for PT inference and call the helper only for ONNX export. Return metadata for the attempt-local ONNX.

- [ ] **Step 5: Verify GREEN**

Run the Task 1 test command and expect all tests to pass.

### Task 3: Persist advisory state without blocking publication

**Files:**
- Modify: `src/yolo_factory/models/gate_runner.py`
- Modify: `src/yolo_factory/models/repository.py`
- Modify: `frontend/src/pages/platform/modelGateDiagnostics.ts`
- Test: `tests/unit/models/test_repository.py`
- Test: `frontend/src/pages/platform/modelGateDiagnostics.test.ts`

- [ ] **Step 1: Write failing repository and diagnostics tests**

Assert `mask_consistency=False` is retained but excluded from hard-gate publication checks, and the frontend labels it as an advisory warning with the failing sample details.

- [ ] **Step 2: Verify RED**

Run backend repository and frontend diagnostics tests; expect failures for the new advisory key.

- [ ] **Step 3: Implement advisory propagation**

Add `mask_consistency` to runner gate output. Exclude `quality_recommended` and `mask_consistency` from repository hard-gate checks. Define the frontend gate as advisory and retain the existing per-sample Mask IoU explanation.

- [ ] **Step 4: Verify GREEN**

Run the Task 3 tests and expect all tests to pass.

### Task 4: End-to-end verification

**Files:**
- Test: `tests/integration/test_model_api.py`

- [ ] **Step 1: Update integration fixture**

Return `mask_consistency` and an attempt-local ONNX path from the fake gate executor; assert the API preserves advisory state without blocking candidate status.

- [ ] **Step 2: Run focused suites**

Run model gate, repository, API, and frontend diagnostics tests. Expect zero failures.

- [ ] **Step 3: Run full verification**

Run backend `python -m pytest -q`, frontend `npm test -- --run`, frontend `npm run build`, and `git diff --check`. Expect zero failures.

- [ ] **Step 4: Verify real artifact preservation**

Record SHA-256 of the current training `best.onnx`, run a gate attempt, and verify the SHA-256 is unchanged. Confirm the new ONNX resides in that attempt's `exported` directory and the report distinguishes hard consistency from mask advisory status.
