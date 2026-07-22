# Manual Training Resource Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an idle-only, cross-platform manual action that reclaims TrainForge-owned regenerable resources and reports the resulting disk and memory state without touching persistent data.

**Architecture:** A focused service composes the existing allowlisted storage cleanup, process-local garbage collection, optional already-loaded CUDA allocator cleanup, disk usage, and the existing cross-platform memory sampler. A guarded FastAPI endpoint exposes the result, while a small React component owns confirmation and result presentation in the training page.

**Tech Stack:** Python 3.10, FastAPI, pytest, React 19, TypeScript, Ant Design, Vitest.

---

### Task 1: Resource cleanup service

**Files:**
- Create: `src/yolo_factory/training/resource_cleanup.py`
- Create: `tests/unit/training/test_resource_cleanup.py`

- [ ] **Step 1: Write failing service tests**

Test injected storage cleanup, garbage collection, disk usage, memory sampling, and an optional CUDA cleanup callback. Assert the result contains storage counters, `python_collected_objects`, `cuda_cache_cleared`, `disk_free_bytes`, `disk_total_bytes`, `resource_snapshot`, and warnings. Add a second test where optional CUDA cleanup raises and assert cleanup still succeeds with a warning.

- [ ] **Step 2: Verify RED**

Run: `$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/unit/training/test_resource_cleanup.py -q`

Expected: collection fails because `resource_cleanup` does not exist.

- [ ] **Step 3: Implement the service**

Create immutable `TrainingResourceCleanupResult` with `model_dump()`. Implement `cleanup_training_resources(storage_root, *, storage_cleanup=cleanup_training_storage, collect=gc.collect, disk_usage=shutil.disk_usage, memory_snapshot=read_training_memory_snapshot, cuda_cleanup=_cleanup_loaded_cuda_cache)`.

`_cleanup_loaded_cuda_cache` must inspect `sys.modules.get("torch")`; it must not import PyTorch into the API process. Return `False` when absent or CUDA unavailable, and call `torch.cuda.empty_cache()` only when the already-loaded module reports availability.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 test and `tests/unit/training/test_storage_cleanup.py`; expect all tests to pass.

- [ ] **Step 5: Commit**

Commit as `feat: add safe training resource cleanup service`.

### Task 2: Idle-only cleanup API

**Files:**
- Modify: `src/yolo_factory/api/app.py`
- Modify: `tests/integration/test_training_api.py`

- [ ] **Step 1: Write failing API tests**

Inject a fake `training_resource_cleanup` into `create_app`. For an idle app, POST `/api/training-resources/cleanup` and assert a structured `200` response. Create a queued training record and assert the endpoint returns `409` without calling cleanup. Keep a separate test proving the endpoint does not alter the counts of training runs, releases, or models.

- [ ] **Step 2: Verify RED**

Run only the new integration tests; expect `404`.

- [ ] **Step 3: Implement endpoint and activity check**

Add the injectable cleanup dependency to `create_app`. Add `@app.post("/api/training-resources/cleanup")` and `@heavy_operation("training-resource-cleanup")`. Reject when any training status is `queued`, `running`, `evaluating`, `exporting`, or `verifying`; the heavy-operation guard handles synchronous model gates, inference, SAM, and dataset release contention. Return `cleanup_training_resources(root).model_dump()`.

- [ ] **Step 4: Verify GREEN**

Run the new integration tests plus all `test_training_api.py`; expect all tests to pass.

- [ ] **Step 5: Commit**

Commit as `feat: expose safe training resource cleanup`.

### Task 3: Typed client and result presentation

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/pages/platform/training/TrainingResourceCleanup.tsx`
- Create: `frontend/src/pages/platform/training/TrainingResourceCleanup.test.tsx`

- [ ] **Step 1: Write failing rendering tests**

Render the component with no result and assert the protected-data explanation and command label exist. Render Windows output and assert released disk, commit memory, physical memory, and `LeASPac` evidence. Render Linux output and assert cgroup current/limit values appear without Windows rows.

- [ ] **Step 2: Verify RED**

Run the component test with Vitest; expect import failure.

- [ ] **Step 3: Implement types and component**

Add `TrainingResourceCleanupResult` and `api.cleanupTrainingResources()`. Build a compact component receiving `pending`, `result`, and `onCleanup`; use an Ant Design confirmation popover, `Trash2` icon, and conditional `Descriptions` rows. Its visible text must state that databases, datasets, annotations, weights, and completed runs are protected, and that external processes are never stopped.

- [ ] **Step 4: Verify GREEN**

Run the component test; expect all tests to pass.

- [ ] **Step 5: Commit**

Commit as `feat: present manual training resource cleanup`.

### Task 4: Training page integration

**Files:**
- Modify: `frontend/src/pages/platform/TrainingPage.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingResourceCleanup.test.tsx`

- [ ] **Step 1: Write failing interaction test**

Test the exported cleanup action controller or component callback contract: one click invokes the API once, pending disables repeats, success stores the result, and rejection shows the API error without discarding the prior result.

- [ ] **Step 2: Verify RED**

Run the focused Vitest test; expect the interaction assertion to fail.

- [ ] **Step 3: Integrate into page**

Add `cleanupPending` and `cleanupResult` state and a `cleanupResources` async handler. Render the cleanup component in the page header action group before Refresh. On success show released-byte feedback and refresh the run list; on failure use the existing `message.error` pattern.

- [ ] **Step 4: Verify GREEN**

Run the focused test and TypeScript production build; expect both to pass.

- [ ] **Step 5: Commit**

Commit as `feat: add cleanup action to training workspace`.

### Task 5: Documentation and full verification

**Files:**
- Modify: `frontend/src/pages/help/helpContent.ts`
- Modify: `README.md`

- [ ] **Step 1: Document exact safety behavior**

Update the bounded-training help entry and README training section. List what is removed, what is protected, idle-only behavior, Windows/Linux evidence, and that TrainForge never terminates external processes.

- [ ] **Step 2: Run backend verification**

Run focused training tests, then `$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest -q`.

- [ ] **Step 3: Run frontend verification**

Run `frontend/node_modules/.bin/vitest.cmd run --pool=threads --maxWorkers=1` and `npm run build` from `frontend`.

- [ ] **Step 4: Verify repository scope**

Run `git diff --check`, `git status --short`, and inspect tracked changes. Confirm no `.db`, dataset, annotation, weight, training-run, cache, or `dist` artifact is included.

- [ ] **Step 5: Commit**

Commit as `docs: explain manual training resource cleanup`.
