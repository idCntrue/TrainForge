# Windows Runtime Memory Threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate Windows training startup and runtime commit-memory thresholds so active training continues at 7.96 GiB while retaining a 4 GiB emergency stop.

**Architecture:** Add a dedicated runtime threshold to `TrainingResourcePolicy`, parse it from the environment, validate its relationship to the startup threshold, and use it only in `validate_runtime_memory_snapshot()`. Preserve the existing exception model so API and frontend diagnostics remain compatible.

**Tech Stack:** Python 3.10, dataclasses, pytest, existing training resource policy.

---

### Task 1: Define the Runtime Threshold Contract

**Files:**
- Modify: `tests/unit/training/test_resource_policy.py`
- Modify: `src/yolo_factory/training/resource_policy.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting:

```python
policy = TrainingResourcePolicy.from_environment({})
assert policy.min_available_commit_gb == 8
assert policy.runtime_min_available_commit_gb == 4

policy.validate_runtime_memory_snapshot({
    "windows_available_commit_bytes": int(7.96 * GIB),
    "windows_available_physical_bytes": int(2.15 * GIB),
})

with pytest.raises(InsufficientTrainingMemory) as captured:
    policy.validate_runtime_memory_snapshot({
        "windows_available_commit_bytes": int(3.99 * GIB),
        "windows_available_physical_bytes": 8 * GIB,
    })
assert captured.value.required_commit_gib == 4
```

Also test environment override, invalid non-positive values, and runtime thresholds greater than startup thresholds.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/training/test_resource_policy.py -q`

Expected: FAIL because `runtime_min_available_commit_gb` does not exist and 7.96 GiB is rejected.

- [ ] **Step 3: Implement the policy field and validation**

Add:

```python
runtime_min_available_commit_gb: int = 4
```

Parse `TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB` with `_positive_integer()`. Reject configurations where the runtime threshold exceeds `min_available_commit_gb`. Refactor `_validate_memory_snapshot()` to accept an explicit `required_commit_gb`; pass the startup value from `validate_memory_snapshot()` and runtime value from `validate_runtime_memory_snapshot()`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/unit/training/test_resource_policy.py -q`

Expected: all resource-policy tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/yolo_factory/training/resource_policy.py tests/unit/training/test_resource_policy.py; git commit -m "fix: relax Windows runtime memory threshold"
```

### Task 2: Verify Runtime Adapter Diagnostics

**Files:**
- Modify: `tests/unit/training/test_ultralytics_adapter.py`
- Modify only if required: `src/yolo_factory/training/ultralytics_adapter.py`

- [ ] **Step 1: Add a regression test**

Test `ensure_training_memory_available()` with 7.96 GiB commit and 2.15 GiB physical and assert no exception. Test 3.99 GiB and assert `TrainingMemoryPressure` still includes both measured values.

- [ ] **Step 2: Verify the focused test**

Run: `python -m pytest tests/unit/training/test_ultralytics_adapter.py -q`

Expected: PASS after Task 1; if the error message does not retain evidence, make the minimal adapter correction and rerun.

- [ ] **Step 3: Commit the regression coverage**

```powershell
git add tests/unit/training/test_ultralytics_adapter.py src/yolo_factory/training/ultralytics_adapter.py; git commit -m "test: cover aggressive Windows runtime memory guard"
```

### Task 3: Document Configuration and Run Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the configuration table**

Clarify the startup-only meaning of `TRAINING_MIN_AVAILABLE_COMMIT_GB` and add:

```markdown
| `TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB` | `4` | Windows 训练运行中的剩余提交内存底线；低于该值时在下一轮前安全停止 |
```

- [ ] **Step 2: Run focused training tests**

Run: `python -m pytest tests/unit/training/test_resource_policy.py tests/unit/training/test_ultralytics_adapter.py tests/unit/training/test_failure_diagnostics.py -q`

Expected: all focused tests pass.

- [ ] **Step 3: Run the complete backend suite**

Run: `python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 4: Check repository state**

Run: `git diff --check; git status --short`

Expected: no whitespace errors and only README changes remain.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md; git commit -m "docs: explain Windows runtime memory threshold"
```
