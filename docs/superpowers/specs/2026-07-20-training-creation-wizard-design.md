# Training Creation Wizard Design

**Date:** 2026-07-20

## Goal

Replace the long training-creation drawer with a four-step wizard and expose the existing Patience, Optimizer, and Close Mosaic controls without weakening server resource protection.

## Interaction Structure

The drawer uses a top `Steps` indicator and a fixed footer. Only one step is rendered at a time so desktop and mobile users do not have to scan or scroll through the entire configuration.

1. **基础设置**
   - Run name
   - Published dataset release
   - Task type inferred from the dataset
   - Selected classes and optional display aliases
   - Official model or uploaded `.pt` weight
2. **训练策略**
   - Device and training preset
   - Epochs, Batch, image size
   - Patience, Optimizer, Close Mosaic
   - CPU/GPU resource warnings
3. **数据增强**
   - Augmentation profile
   - Mosaic, MixUp, Copy-Paste, rotation, translation, scale, horizontal flip, and HSV controls
4. **确认启动**
   - Human-readable summary of dataset, model source, device, resource settings, training strategy, and augmentation profile
   - Early-stopping explanation
   - Storage/resource warning area

The footer contains `上一步`, `下一步`, and, on the final step, `加入队列`. The footer remains visible while step content scrolls. Closing the drawer resets the current step, form, upload state, and storage error.

## Step Validation

`下一步` validates only the fields owned by the current step. Users remain on the step containing an error and the first invalid field is visible. The final submission validates the complete form.

- Step 1 requires name, dataset, inferred task, at least one class, and a valid official model or uploaded `.pt` file.
- Step 2 requires valid device and strategy values.
- Step 3 validates augmentation ranges.
- Step 4 has no editable fields and submits only after the complete form passes.

## Preset Behavior

Preset values are defined once in a frontend presentation module matching the backend presets:

| Preset | Epochs | Image | Patience | Optimizer | Close Mosaic | Profile |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| 流程验证 | 10 | 320 | 5 | Auto | 2 | Conservative |
| CPU 均衡训练 | 150 | 640 | 25 | Auto | 10 | Conservative |
| GPU 高质量训练 | 200 | 640 | 30 | Auto | 10 | Standard |

Batch remains task/device dependent: smoke uses 1; CPU detect uses 2; CPU segment uses 1; GPU quality uses 8.

Selecting a preset writes all visible strategy and augmentation values into the form. Editing Epochs, Batch, image size, Patience, Optimizer, Close Mosaic, or any augmentation value immediately changes `presetId` to `custom`. This is required because the backend intentionally replaces request values when a named preset is submitted.

Changing task or device reapplies only the resource-safe Batch rule when a named preset is active. GPU quality remains unavailable on CPU.

## Advanced Training Parameters

### Patience

- Integer range: `0..300` in the UI.
- `0` disables early stopping and attempts all configured epochs.
- Positive values mean training completes normally after that many epochs without a new best validation score.
- Help text states that `best.pt`, not necessarily `last.pt`, is used for candidate-model registration.

### Optimizer

- Select options: `auto`, `SGD`, `Adam`, `AdamW`.
- `auto` remains recommended for general users.
- Backend request validation accepts only these values, case-normalized to the Ultralytics spelling.

### Close Mosaic

- Integer range: `0..epochs`.
- `0` means Mosaic is not explicitly closed before the final epochs.
- The form revalidates Close Mosaic when Epochs changes.
- Backend rejects `close_mosaic > epochs` for defense in depth.

## API and Persistence

No SQLite schema migration is required. The existing `config_json`, request schema, domain model, manifest, and Ultralytics adapter already support all three fields.

Both creation paths must submit the same fields:

- regular JSON training creation;
- custom `.pt` multipart upload.

The frontend repository currently omits Patience, Optimizer, Close Mosaic, and augmentation profile and must be corrected. The custom-weight request currently omits the same strategy fields and augmentation values and must be corrected.

## Training Detail Feedback

The parameter/artifact tab adds a reproducibility block showing:

- preset;
- Epochs and completed epochs;
- Patience;
- Optimizer;
- Close Mosaic;
- augmentation profile.

For an early-stopped completed run, the overview displays:

> 最佳轮次 49，连续 20 轮未改善，于第 70 轮提前停止。训练正常完成，候选模型使用 best.pt。

Historical runs without structured early-stop fields use the existing generic completed message.

## Responsive Layout

- Desktop drawer width increases to approximately `720px`, while step content remains constrained for comfortable reading.
- Mobile uses the existing full-screen drawer.
- The step labels use short Chinese names and remain readable at `390px`; descriptions move into the step body rather than the step header.
- The fixed footer accounts for mobile safe-area padding and never overlaps fields.
- Form controls use one column on mobile and two columns where space permits on desktop.

## Error Handling

- Storage errors remain visible on the confirmation step and return the user to the relevant strategy step when configuration changes are needed.
- Upload progress remains in Step 1 and submission stays disabled while an upload is incomplete.
- CPU limits continue to normalize and validate Batch/image size.
- Named preset values remain authoritative unless the form has switched to `custom`.

## Testing

Backend tests cover optimizer allowlisting, `close_mosaic <= epochs`, preset resolution, regular creation, and uploaded-weight creation.

Frontend tests cover:

- initial wizard step and step-specific validation;
- Back/Next transitions and reset on close;
- preset-to-form value mapping;
- manual edits switching to Custom;
- Patience `0` and upper bound;
- Close Mosaic revalidation against Epochs;
- complete payload parity for JSON and custom-weight requests;
- confirmation summary and early-stop explanation;
- desktop and mobile rendering without horizontal overflow.

## Acceptance Criteria

- Users can configure Patience, Optimizer, and Close Mosaic before training.
- The meaning of early stopping and `best.pt` is understandable without reading logs.
- All current creation features remain available in the wizard.
- Preset and custom values cannot silently disagree.
- Regular and uploaded-weight training use identical strategy fields.
- Server resource limits and existing runtime/database data remain unchanged.
