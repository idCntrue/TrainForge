# Dataset Storage Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only dataset registry/storage diagnostics and safe registration of fully validated orphan release directories.

**Architecture:** A focused reconciliation service owns filesystem scanning and repair validation. FastAPI exposes the service through two endpoints, while the existing dataset workspace adds a responsive diagnostic drawer without changing release or training behavior.

**Tech Stack:** Python 3.10, SQLAlchemy 2, FastAPI, PyYAML, React 19, TypeScript 5.8, Ant Design 5, Vitest, pytest.

---

### Task 1: Define reconciliation behavior

**Files:**
- Create: `tests/unit/datasets/test_reconciliation.py`
- Create: `src/yolo_factory/datasets/reconciliation.py`

- [ ] Write failing tests that create temporary registry records and release trees for `healthy`, `missing_artifacts`, `orphan_directory`, invalid manifest, failed checksum, missing provenance, unsafe paths, and successful registration.
- [ ] Run `python -m pytest tests/unit/datasets/test_reconciliation.py -q` and confirm failures are caused by the missing module.
- [ ] Implement `DatasetReconciliationFinding`, `scan_dataset_releases`, checksum/path validation, and `register_orphan_release` with no filesystem mutation.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Expose reconciliation APIs

**Files:**
- Modify: `src/yolo_factory/api/schemas.py`
- Modify: `src/yolo_factory/api/app.py`
- Create: `tests/integration/test_dataset_reconciliation_api.py`

- [ ] Write failing API tests for scan output, successful orphan registration, and rejected invalid registration.
- [ ] Run `python -m pytest tests/integration/test_dataset_reconciliation_api.py -q` and confirm the endpoints return 404.
- [ ] Add response/request schemas and `GET /api/dataset-releases/reconciliation` plus `POST /api/dataset-releases/reconciliation/register`.
- [ ] Re-run the API tests and focused unit tests.

### Task 3: Add dataset reconciliation UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/appShellLayout.test.ts`

- [ ] Add a failing frontend contract test for `dataset-reconciliation-trigger`, `dataset-reconciliation-drawer`, `dataset-reconciliation-summary`, `dataset-reconciliation-finding`, and `重新注册`.
- [ ] Run `npm test -- --run src/appShellLayout.test.ts` and confirm it fails on the missing contract.
- [ ] Add typed API clients, a scan button, diagnostic drawer, status summaries, finding list, and confirmed register action.
- [ ] Add responsive styles that keep actions at least 44px on mobile and avoid nested cards.
- [ ] Re-run the focused frontend test.

### Task 4: Verify and commit

**Files:**
- Verify all files changed above.

- [ ] Run `python -m pytest -q` and confirm the backend suite passes.
- [ ] Run `npm test -- --run` from `frontend` and confirm the frontend suite passes.
- [ ] Run `npm run build` from `frontend` and confirm the production build succeeds.
- [ ] Run `git diff --check` and inspect the complete diff for data-destructive behavior.
- [ ] Commit the implementation without merging or modifying deployment data.
