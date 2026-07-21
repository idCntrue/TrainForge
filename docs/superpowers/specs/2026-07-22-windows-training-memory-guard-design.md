# Windows Training Memory Guard Design

## Goal

Prevent long-running Windows training jobs from crashing inside native OpenCV code when system commit memory is exhausted, and replace opaque `runner_failed / exit 3221225477` diagnostics with an actionable resource-limit explanation.

The guard must not terminate unrelated processes, mutate datasets, modify SQLite records outside the normal training lifecycle, or change Linux container behavior.

## Confirmed Failure

The observed Windows failure has all of these signals:

- process exit code `3221225477` (`0xC0000005`);
- Windows Event Log identifies `cv2.pyd` as the faulting module;
- repeated `LeASPac.exe` processes consume tens of GiB of committed memory;
- GPU memory remains below capacity;
- Python exits before it can write a traceback.

Large source images increase transient OpenCV decode allocations, but they are not corrupt and are not the root cause. The durable operating-system fix is to repair or disable the leaking Lenovo service. The application guard provides early detection and clear recovery guidance.

## Design

### Windows Resource Snapshot

Add a platform-neutral training resource snapshot API. On Linux it continues to report cgroup values. On Windows it additionally reports:

- physical memory total and available;
- commit limit, committed bytes, and available commit bytes;
- page-file allocation and usage when available;
- count and aggregate private bytes for `LeASPac.exe`;
- the highest private-memory processes as bounded diagnostic evidence.

Windows metrics use `ctypes` and standard Windows APIs so no new runtime dependency is required. Missing or denied metrics return `None` instead of breaking training.

### Start Gate

Before creating the runner process, reject a Windows training start when either condition is true:

- available commit memory is below the configured minimum; or
- available physical memory is below the configured minimum.

Defaults:

- `TRAINING_MIN_AVAILABLE_COMMIT_GB=8`;
- `TRAINING_MIN_AVAILABLE_MEMORY_GB=4`.

The rejection includes current values and, when present, the `LeASPac.exe` process count and aggregate private memory. Linux ignores these Windows-only gates.

### Runtime Guard

The runner checks Windows memory at the beginning of every training epoch through an Ultralytics callback. If a threshold is crossed, it raises a dedicated Python exception before the next epoch starts. The previous epoch's `last.pt` remains available, and the normal runner exception path writes a structured failure event.

The runtime guard does not kill system processes and does not alter the configured Batch, image size, or augmentation automatically.

### Failure Classification

Classify the following as `resource_limit` with Windows/OpenCV-specific guidance:

- unsigned exit code `3221225477` or signed equivalent `-1073741819`;
- `0xC0000005` combined with OpenCV evidence;
- the dedicated runtime memory-guard exception.

The failure diagnostic records the Windows memory snapshot captured after runner exit. The UI continues to consume the existing structured diagnostic contract, so it can show the improved summary, action, evidence, and resource values without a new database schema.

### Recovery

When `best.pt` or `last.pt` exists, diagnostics state that the weight is preserved. The guard does not automatically resume training because the existing retry workflow creates a new run and automatic process resumption would require a separate lifecycle design.

## Error Messages

Start rejection:

> Windows 可用提交内存不足，无法安全启动训练。当前剩余 X GiB，至少需要 Y GiB。检测到 LeASPac.exe N 个，共占用 Z GiB；请停止异常的 LenovoServiceAS 后重试。

Runtime failure:

> Windows 提交内存已接近耗尽，训练已在下一轮开始前安全停止，已保存的权重不会被删除。

Native crash classification:

> OpenCV 原生进程因 Windows 内存压力异常退出（0xC0000005）。请检查 LenovoServiceAS/LeASPac 和系统提交内存后重试。

## Testing

- Unit-test Windows snapshot normalization using injected API readings.
- Unit-test start-gate allow/reject behavior and Linux no-op behavior.
- Unit-test runtime callback raising only below threshold.
- Unit-test signed and unsigned access-violation exit-code classification.
- Verify existing cgroup, executor, failure-diagnostic, API, and frontend diagnostic tests remain green.

## Safety

- No automatic service stop, process kill, registry change, or startup-type change.
- No database migration.
- No mutation of existing run directories, datasets, labels, or weights.
- No behavioral change on Linux unless existing cgroup logic already applies.
