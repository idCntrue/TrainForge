# TrainForge Desktop Launcher Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create safe one-click Windows desktop launch and shutdown scripts for the local TrainForge API and frontend.

**Architecture:** Two visible CMD wrappers invoke two hidden PowerShell helpers. The start helper validates paths, starts only missing listeners, performs HTTP readiness checks, and opens the training page; the stop helper requires explicit confirmation and terminates only processes listening on the two TrainForge ports.

**Tech Stack:** Windows CMD, Windows PowerShell 5.1, Uvicorn, Vite.

---

### Task 1: Create the Start Launcher

**Files:**
- Create: `C:\Users\chenNuo\Desktop\启动 TrainForge.cmd`
- Create: `C:\Users\chenNuo\Desktop\TrainForge-start.ps1`

- [ ] Create a CMD wrapper that sets UTF-8, invokes the helper with execution-policy bypass, reports its exit code, and pauses on failure.
- [ ] Create a PowerShell helper with `Test-Listener`, `Wait-Http`, and `Fail-Launch` functions.
- [ ] Validate Python, npm, worktree root, frontend directory, and main-worktree `system.yaml` before starting anything.
- [ ] Start API only when port 8000 is free, inheriting `PYTHONPATH` and `YOLO_FACTORY_SYSTEM_CONFIG`.
- [ ] Start frontend only when port 53257 is free.
- [ ] Wait up to 30 seconds per service, show the relevant error-log tail on failure, then open the training URL on success.

### Task 2: Create the Stop Launcher

**Files:**
- Create: `C:\Users\chenNuo\Desktop\关闭 TrainForge.cmd`
- Create: `C:\Users\chenNuo\Desktop\TrainForge-stop.ps1`

- [ ] Create a CMD wrapper with UTF-8 output and PowerShell execution-policy bypass.
- [ ] List process id, process name, and listening port for 8000 and 53257.
- [ ] Require the exact confirmation text `CLOSE`; all other input exits without mutation.
- [ ] Stop only the unique listener process ids and verify both ports are released.

### Task 3: Verify Safety and Startup

- [ ] Parse both PowerShell helpers with `[scriptblock]::Create()` and fail on syntax errors.
- [ ] Verify both CMD wrappers reference existing helpers.
- [ ] Mark the PowerShell helpers hidden while leaving CMD wrappers visible.
- [ ] Run the start helper against current services and confirm API health reports `D:\YOLO_DATA` and the training page returns HTTP 200.
- [ ] Run the stop helper with a non-confirming response and verify existing listener process ids are unchanged.
- [ ] Report the four created paths and log locations to the user.
