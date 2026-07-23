# Model Gate History Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** List and safely delete isolated model-gate attempts and their files from the model details page.

**Architecture:** A focused filesystem inventory service reads attempt directories; API orchestration applies active fallback/reset rules through the model repository before deleting files. The frontend adds typed API methods and a responsive history panel with consequence-specific confirmation text.

**Tech Stack:** Python 3.10, pathlib, FastAPI, SQLAlchemy repository, React 19, TypeScript, Ant Design, Vitest, pytest.

---

### Task 1: Gate-run filesystem inventory

**Files:**
- Create: `src/yolo_factory/models/gate_history.py`
- Create: `tests/unit/models/test_gate_history.py`

- [ ] Write failing tests for newest-first listing, complete and incomplete attempts, aggregate size, active-path matching, and safe run-id/path validation.
- [ ] Run the unit test and confirm RED.
- [ ] Implement immutable inventory dictionaries and safe path resolution limited to the model's direct `gate-runs` children.
- [ ] Run the unit test and confirm GREEN.

### Task 2: Repository fallback and reset

**Files:**
- Modify: `src/yolo_factory/models/repository.py`
- Modify: `tests/unit/models/test_repository.py`

- [ ] Write failing tests for activating an older result and resetting runtime gates while preserving independent test and quality advisory state.
- [ ] Run tests and confirm RED.
- [ ] Add focused repository methods for applying a gate snapshot and clearing active gate output.
- [ ] Run tests and confirm GREEN.

### Task 3: History list and delete API

**Files:**
- Modify: `src/yolo_factory/api/schemas.py`
- Modify: `src/yolo_factory/api/app.py`
- Modify: `tests/integration/test_model_api.py`

- [ ] Write failing integration tests for history listing, historical deletion, active fallback, last-active reset, published-active rejection, and traversal rejection.
- [ ] Run tests and confirm RED.
- [ ] Implement typed list/delete endpoints using the inventory and repository methods.
- [ ] Delete only after fallback/reset succeeds and return deleted byte count plus fallback metadata.
- [ ] Run tests and confirm GREEN.

### Task 4: Responsive history UI

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/pages/platform/ModelGateHistoryPanel.tsx`
- Create: `frontend/src/pages/platform/ModelGateHistoryPanel.test.tsx`
- Modify: `frontend/src/pages/platform/ModelsPage.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Write failing presentation tests for active/history badges, mobile cards, file sizes, fallback text, last-run text, and published protection.
- [ ] Run tests and confirm RED.
- [ ] Add typed API methods and the responsive panel using existing design-system components and icons.
- [ ] Integrate loading, deletion, refresh, confirmations, and actionable Chinese success/error feedback into the model drawer.
- [ ] Run tests and confirm GREEN.

### Task 5: Verification

**Files:**
- Modify tests only if verification exposes a real regression.

- [ ] Run focused backend and frontend suites.
- [ ] Run the complete backend suite.
- [ ] Run the complete frontend suite and production build.
- [ ] Run `git diff --check`.
- [ ] Verify with temporary real files that deleting a gate attempt leaves training `best.pt` and `best.onnx` hashes unchanged.
