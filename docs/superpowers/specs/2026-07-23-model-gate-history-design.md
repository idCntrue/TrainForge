# Model Gate History Management Design

## Goal

Expose every isolated model-gate attempt in the model details UI and safely delete an attempt together with its ONNX, report, log, and comparison images without ever deleting training artifacts.

## Source of truth

Gate history is derived from directories under:

```text
model-versions/{model_id}/gate-runs/{run_id}/
```

No new database table or migration is required. The API parses each attempt's manifest, result, files, timestamps, and total size. The model version's `gate_report_path` identifies the active attempt. Existing gate directories become visible immediately.

## API

- `GET /api/model-versions/{model_id}/gate-runs` lists newest-first attempts.
- `DELETE /api/model-versions/{model_id}/gate-runs/{run_id}` deletes one attempt and its files.

Each list item includes the run id, created time, status, active flag, gate results, ONNX metadata, report path, total size, and available diagnostics. Invalid or incomplete attempts remain visible with an explanatory status rather than breaking the list.

## Deletion policy

- Historical attempts can be deleted directly.
- Deleting the active attempt selects the newest remaining completed attempt and atomically updates the model's gates, artifacts, environment, and report path before removing the old directory.
- If no completed attempt remains, the model is reset to pending gates: runtime gates become false, the original training PT remains referenced, the gate ONNX reference is removed, and independent-test quality evidence is preserved.
- The active attempt of a published model cannot be deleted. The API returns a clear conflict explaining that the model must be archived or a newer gate must become active first.
- Only a direct child directory of the target model's `gate-runs` root may be deleted. Symlinks, traversal, malformed ids, and paths outside the storage root are rejected.
- Training files under `training-runs` and imported model files are never deletion targets.

The database pointer is changed before filesystem cleanup. If cleanup then fails, the API reports the failure while leaving a valid active reference; the old unreferenced directory can be retried. Historical deletion has no database mutation.

## User experience

The model drawer gains a `门禁历史` section below the current diagnostics. Desktop uses a compact table; mobile uses single-column record cards. Each record shows current/history state, run time, hard consistency, mask advisory, ONNX size, total size, and a collapsible file/path summary.

Deletion confirmation explains the exact consequence:

- History: removes only this gate's files and does not affect the current model.
- Active with fallback: automatically switches to the named previous gate.
- Last active: returns the model to `待运行门禁`; training `best.pt` and `best.onnx` remain untouched.
- Published active: deletion is disabled with archive/new-gate guidance.

Success feedback states the freed byte count and fallback target. Error feedback translates conflict, missing-file, and cleanup failures into actionable Chinese text.

## Compatibility

All paths are produced and validated with `pathlib`, so Windows local storage and Linux/Docker `/data` storage use the same behavior. Existing models without isolated attempts return an empty history and retain current diagnostics.

## Verification

- Unit tests cover inventory parsing, ordering, incomplete attempts, path validation, and directory sizes.
- Repository/API tests cover historical deletion, active fallback, last-attempt reset, and published protection.
- Frontend tests cover desktop/mobile presentation and all confirmation messages.
- A real temporary storage test confirms gate-run files are removed while training `best.pt` and `best.onnx` hashes remain unchanged.
