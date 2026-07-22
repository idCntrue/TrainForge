# Manual Training Resource Cleanup Design

## Goal

Add a cross-platform manual action that safely reclaims TrainForge-owned, regenerable resources and immediately reports the resulting disk and memory state. The action must work on Windows development machines and Linux cloud deployments without changing persistent training data.

## Safety Boundary

The cleanup may remove only content already covered by the existing `cleanup_training_storage` policy: annotation thumbnails, stale temporary uploads, and stale partial or temporary training content. It may request Python garbage collection and, when PyTorch is already loaded and CUDA is available, release unused CUDA allocator cache.

The cleanup must never delete or rewrite:

- SQLite databases or backups;
- source videos, extracted frames, annotations, or dataset releases;
- model weights, exports, DVC objects, or completed training artifacts;
- active training directories or files;
- environment files or deployment configuration.

It must never terminate `LeASPac.exe`, `LenovoServiceAS`, Docker, Python training workers, or any other operating-system process. External process evidence is diagnostic only.

## Backend Design

Introduce a small training resource cleanup service that composes existing safe storage cleanup with process-local memory cleanup. It returns a structured result containing:

- released disk bytes and removed-item counts from the existing storage cleanup result;
- whether Python garbage collection ran;
- whether CUDA cache cleanup was available and attempted;
- the post-cleanup cross-platform resource snapshot;
- warnings for unavailable optional cleanup mechanisms.

Expose the service through `POST /api/training-resources/cleanup`. The endpoint is rejected with `409` while a training run or another GPU-heavy operation is active, because cleaning allocator state during active work is misleading and may contend with that work. The endpoint does not create training records and does not open or mutate the registry database beyond the read needed to determine whether work is active.

The endpoint is idempotent: invoking it repeatedly is safe and may simply report zero newly released bytes.

## Frontend Design

Add a compact `释放训练资源` command in the training workspace resource area, not as a global destructive action. Before execution, show a confirmation that lists the protected data categories. While running, disable repeat submission.

After completion, show:

- released disk space;
- current free disk when available;
- Windows available commit and physical memory when available;
- `LeASPac` process count and private bytes when detected, with a note that TrainForge did not stop it;
- cgroup memory data on Linux when available;
- warnings returned by the backend.

The result uses the existing quiet operational UI style and does not claim that external-process memory was released.

## Error Handling

- `409`: active training or heavy operation; tell the user to wait or cancel that operation first.
- `500`: unexpected cleanup failure; preserve all persistent data and display the technical message.
- Optional CUDA cleanup unavailable: return success with a warning, because storage cleanup and resource sampling remain useful.

## Compatibility

Windows uses the new Win32 snapshot fields already provided by the memory guard. Linux uses existing cgroup and disk readings. No database schema migration, Docker volume change, or deployment data migration is required.

## Testing

- Unit tests prove the service invokes only the allowlisted storage cleanup and reports post-cleanup snapshots.
- Unit tests prove missing PyTorch/CUDA support is non-fatal.
- Integration tests prove the endpoint succeeds when idle and returns `409` during active work.
- Frontend tests prove confirmation, pending state, protected-data wording, and Windows/Linux result rendering.
- Full backend and frontend suites plus the production frontend build must pass.
