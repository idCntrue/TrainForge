# Model Gate Isolation and Segmentation Consistency Design

## Goal

Prevent model-gate execution from overwriting an existing training ONNX artifact, while keeping useful PT/ONNX compatibility checks for segmentation models without rejecting deployable models solely because thin masks differ by a few pixels.

## Artifact isolation

Each gate attempt owns its exported ONNX under:

```text
model-versions/{model_id}/gate-runs/{attempt_id}/exported/best.onnx
```

The gate runner copies the source PT into the attempt-local export directory and exports from that copy. Ultralytics therefore writes beside the copy and cannot replace `training-runs/.../weights/best.onnx`. The temporary PT copy is removed after export. Existing training and imported model artifacts remain untouched.

Every attempt retains its report, comparison images, log, and ONNX for auditability. The model repository continues to reference the newest completed attempt. No automatic deletion is introduced.

## Gate policy

The following remain hard requirements:

- training completed;
- PT artifact loads;
- ONNX export exists and loads;
- PT and ONNX return the same number of detections;
- matched detections have the same class;
- box IoU is at least `0.80`;
- confidence delta is at most `0.15`.

For segmentation, mask IoU remains measured and reported with the existing `0.75` recommendation. A mask-only mismatch becomes advisory when all hard detection requirements pass. This accommodates small and thin masks whose pixel IoU is unstable after ONNX export while still exposing the exact sample, score, and comparison overlay.

The report adds an explicit mask-consistency advisory result so the UI can distinguish a deploy-blocking incompatibility from a mask fidelity warning. Publication is allowed when all hard requirements pass; independent test-set quality remains a separate release signal.

## Data flow

1. API creates a unique gate attempt directory.
2. Executor writes the manifest there.
3. Runner copies PT into the attempt-local export directory.
4. Runner exports and evaluates the isolated ONNX.
5. Runner records hard consistency and mask advisory results.
6. Repository stores the latest gate report and attempt-local ONNX metadata.

## Failure handling

- Failed export leaves the original PT and any existing ONNX unchanged.
- A missing or unloadable ONNX remains a hard failure.
- Class/count/box/confidence incompatibility remains a hard failure.
- Mask-only mismatch is clearly reported as a warning and does not silently pass.

## Verification

- Unit test proves export operates on an attempt-local PT path.
- Unit tests prove mask-only mismatch is advisory while box/count/class mismatch remains blocking.
- Integration tests prove artifact metadata references the attempt-local ONNX.
- Existing inference, model API, and full backend suites remain green.
- A real gate run verifies the training-directory ONNX SHA-256 is unchanged before and after execution.
