# Windows Training Memory Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect Windows commit-memory exhaustion before native OpenCV crashes, stop training safely between epochs, and explain `0xC0000005/cv2.pyd` failures clearly.

**Architecture:** Extend the existing resource snapshot and policy layers instead of adding a parallel monitor. The executor applies the start gate, the Ultralytics adapter applies the epoch gate, and the existing failure diagnostic contract carries evidence to the current UI without a schema migration.

**Tech Stack:** Python 3.10, ctypes Win32 APIs, Ultralytics callbacks, pytest, existing FastAPI/React diagnostic contract.

---

### Task 1: Windows memory snapshot

**Files:**
- Modify: `src/yolo_factory/training/resource_snapshot.py`
- Test: `tests/unit/training/test_resource_snapshot.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests that pass injected memory and process readings and expect stable byte fields:

```python
def test_builds_windows_memory_snapshot_with_leaspac_evidence() -> None:
    snapshot = build_windows_memory_snapshot(
        total_physical=16 * GIB,
        available_physical=5 * GIB,
        commit_limit=64 * GIB,
        available_commit=6 * GIB,
        processes=[("LeASPac.exe", 11, 2 * GIB), ("python.exe", 22, 4 * GIB)],
    )
    assert snapshot["windows_committed_bytes"] == 58 * GIB
    assert snapshot["windows_available_commit_bytes"] == 6 * GIB
    assert snapshot["windows_leaspac_process_count"] == 1
    assert snapshot["windows_leaspac_private_bytes"] == 2 * GIB
```

Also assert `read_training_memory_snapshot(platform_name="posix")` preserves the existing cgroup keys.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_resource_snapshot.py -q`

Expected: import failures for the new functions.

- [ ] **Step 3: Implement standard-library Win32 sampling**

Add `build_windows_memory_snapshot(...)`, private ctypes readers for `GlobalMemoryStatusEx`, Toolhelp process enumeration, and process private bytes via `GetProcessMemoryInfo`. Add:

```python
def read_training_memory_snapshot(*, platform_name: str | None = None) -> dict[str, int | None]:
    platform_name = platform_name or os.name
    if platform_name != "nt":
        return read_cgroup_memory_snapshot()
    try:
        return _read_windows_memory_snapshot()
    except (OSError, ValueError):
        return _empty_windows_memory_snapshot()
```

All Win32 handles must be closed in `finally`; access-denied processes are skipped.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_resource_snapshot.py -q`

Expected: all resource snapshot tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/yolo_factory/training/resource_snapshot.py tests/unit/training/test_resource_snapshot.py
git commit -m "feat: capture Windows training memory pressure"
```

### Task 2: Configurable start and runtime policy

**Files:**
- Modify: `src/yolo_factory/training/resource_policy.py`
- Test: `tests/unit/training/test_resource_policy.py`

- [ ] **Step 1: Write failing threshold tests**

Test defaults and overrides for `TRAINING_MIN_AVAILABLE_COMMIT_GB=8` and `TRAINING_MIN_AVAILABLE_MEMORY_GB=4`. Add allow/reject cases:

```python
with pytest.raises(InsufficientTrainingMemory) as error:
    policy.validate_memory_snapshot({
        "windows_available_commit_bytes": 3 * GIB,
        "windows_available_physical_bytes": 5 * GIB,
        "windows_leaspac_process_count": 30,
        "windows_leaspac_private_bytes": 31 * GIB,
    })
assert error.value.as_detail()["leaspac_process_count"] == 30
```

An all-`None` or cgroup-only snapshot must be accepted so Linux behavior is unchanged.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_resource_policy.py -q`

Expected: missing policy fields and exception.

- [ ] **Step 3: Implement policy and actionable exception**

Add `InsufficientTrainingMemory` with `as_detail()` and these fields to `TrainingResourcePolicy`:

```python
min_available_commit_gb: int = 8
min_available_memory_gb: int = 4
```

Implement `validate_memory_snapshot(snapshot)` using byte comparisons and a Chinese message that includes available memory, configured thresholds, and LeASPac evidence when present.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_resource_policy.py -q`

Expected: all resource policy tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/yolo_factory/training/resource_policy.py tests/unit/training/test_resource_policy.py
git commit -m "feat: gate unsafe Windows training memory"
```

### Task 3: Enforce the start gate

**Files:**
- Modify: `src/yolo_factory/training/executor.py`
- Test: `tests/unit/training/test_executor.py`

- [ ] **Step 1: Write a failing executor test**

Inject a low Windows snapshot, call `start()`, assert `InsufficientTrainingMemory`, and assert `subprocess.Popen` was never called and no run directory was created.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_executor.py -q`

Expected: the fake process starts instead of being rejected.

- [ ] **Step 3: Apply the gate before filesystem/process mutation**

Replace direct cgroup sampling with `read_training_memory_snapshot()` and call:

```python
initial_resources = read_training_memory_snapshot()
self._resource_policy.validate_memory_snapshot(initial_resources)
```

This must happen before `run_directory.mkdir(...)`. Persist the accepted snapshot to `process.json`, and use the same snapshot API when writing failure diagnostics.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_executor.py -q`

Expected: all executor tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/yolo_factory/training/executor.py tests/unit/training/test_executor.py
git commit -m "feat: block training under Windows memory pressure"
```

### Task 4: Stop safely between epochs

**Files:**
- Modify: `src/yolo_factory/training/ultralytics_adapter.py`
- Test: `tests/unit/training/test_ultralytics_adapter.py`

- [ ] **Step 1: Write failing callback tests**

Add a `TrainingMemoryPressure` test that injects a low snapshot into a pure helper:

```python
with pytest.raises(TrainingMemoryPressure, match="提交内存"):
    ensure_training_memory_available(policy, low_snapshot)
```

Test an accepted snapshot and a Linux snapshot as no-ops.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_ultralytics_adapter.py -q`

Expected: missing helper and exception.

- [ ] **Step 3: Register an epoch-start guard**

Create `TrainingMemoryPressure(RuntimeError)` and `ensure_training_memory_available(...)`. Construct policy from the runner environment, then register:

```python
def on_train_epoch_start(trainer) -> None:
    del trainer
    ensure_training_memory_available(policy, read_training_memory_snapshot())

model.add_callback("on_train_epoch_start", on_train_epoch_start)
```

Keep the existing `on_fit_epoch_end` telemetry callback unchanged.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_ultralytics_adapter.py -q`

Expected: adapter tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/yolo_factory/training/ultralytics_adapter.py tests/unit/training/test_ultralytics_adapter.py
git commit -m "feat: stop training before Windows memory crash"
```

### Task 5: Classify native OpenCV access violations

**Files:**
- Modify: `src/yolo_factory/training/failure_diagnostics.py`
- Modify: `src/yolo_factory/training/executor.py`
- Test: `tests/unit/training/test_failure_diagnostics.py`

- [ ] **Step 1: Write failing signed/unsigned exit-code tests**

For `3221225477` and `-1073741819`, assert `resource_limit`, Windows/OpenCV wording, preserved epoch, and evidence containing `0xC0000005`. Also test `TrainingMemoryPressure` text.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_failure_diagnostics.py -q`

Expected: current fallback is `runner_failed`.

- [ ] **Step 3: Implement precise classification**

Give access-violation exit codes priority after SIGKILL handling:

```python
elif exit_code in {3221225477, -1073741819}:
    code = "resource_limit"
    evidence.append("Windows native access violation 0xC0000005; cv2.pyd commonly crashes when commit memory is exhausted")
```

Use a Windows-specific presentation string when this evidence exists. Ensure executor failure snapshots use `read_training_memory_snapshot()` so diagnostics include commit and LeASPac values.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_failure_diagnostics.py tests/unit/training/test_executor.py -q`

Expected: both suites pass.

- [ ] **Step 5: Commit**

```bash
git add src/yolo_factory/training/failure_diagnostics.py src/yolo_factory/training/executor.py tests/unit/training/test_failure_diagnostics.py
git commit -m "fix: explain Windows OpenCV memory crashes"
```

### Task 6: Surface memory evidence in the existing UI

**Files:**
- Modify: `frontend/src/pages/platform/training/TrainingFailurePanel.tsx`
- Modify: `frontend/src/pages/platform/training/TrainingFailurePanel.test.tsx`

- [ ] **Step 1: Write a failing rendering test**

Pass a resource snapshot containing available commit, physical memory, and LeASPac values. Assert the rendered HTML contains `剩余提交内存`, `LeASPac`, `30 个`, and `31.00 GiB`.

- [ ] **Step 2: Verify RED**

Run: `frontend/node_modules/.bin/vitest.cmd run frontend/src/pages/platform/training/TrainingFailurePanel.test.tsx --pool=threads --maxWorkers=1`

Expected: memory evidence is absent.

- [ ] **Step 3: Render a compact Windows memory description**

Build `Descriptions` items only when corresponding snapshot values are numeric. Convert bytes to GiB with two decimals. Do not show empty Windows fields on Linux failures.

- [ ] **Step 4: Verify GREEN**

Run the same Vitest command; expect all panel tests to pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/platform/training/TrainingFailurePanel.tsx frontend/src/pages/platform/training/TrainingFailurePanel.test.tsx
git commit -m "feat: show Windows memory evidence in training failures"
```

### Task 7: Configuration and regression verification

**Files:**
- Modify: `.env.docker.example`
- Modify: `README.md`

- [ ] **Step 1: Document the two thresholds**

Add the environment variables with defaults and state that they apply only when Windows metrics are available. Document that the platform never stops `LenovoServiceAS` automatically.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
python -m pytest tests/unit/training/test_resource_snapshot.py tests/unit/training/test_resource_policy.py tests/unit/training/test_executor.py tests/unit/training/test_ultralytics_adapter.py tests/unit/training/test_failure_diagnostics.py -q
```

Expected: all focused tests pass.

- [ ] **Step 3: Run full backend regression**

Run: `python -m pytest -q`

Expected: no failures.

- [ ] **Step 4: Run frontend regression and build**

Run:

```powershell
Set-Location frontend; .\node_modules\.bin\vitest.cmd run --pool=threads --maxWorkers=1; npm run build
```

Expected: all tests and production build pass.

- [ ] **Step 5: Verify scope and commit docs**

Run `git diff --check` and inspect `git status --short`. Confirm no database, weight, run artifact, or generated frontend output is tracked.

```bash
git add .env.docker.example README.md
git commit -m "docs: configure Windows training memory guard"
```
