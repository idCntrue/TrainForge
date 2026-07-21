# Training Metrics Explainability Design

## Goal

Improve the running-training detail drawer for both algorithm users and beginners without changing training execution, API polling, persistence, or backend resource usage.

## Scope

- Use only `epoch_history`, `latest_metrics`, timing, configuration, and run summary data already returned by the details API.
- Compute presentation summaries in the browser: latest value, best value and epoch, recent trend, reference band, and evidence-based health observations.
- Update the overview and charts tabs plus their responsive styles and focused frontend tests.
- Do not modify Python, the database, training arguments, worker processes, API endpoints, or polling intervals.
- Do not add hardware telemetry because it is not present in the current details response.

## Information Architecture

### Overview

Keep the progress area compact and show six readable metrics for segmentation runs: Mask mAP50, Mask mAP50-95, precision, recall, training/validation Mask Loss, and ETA. Detection runs use the equivalent box metrics.

Each quality metric includes the latest value, best value and epoch, a recent trend, and one sentence describing what the value means. The newest usable epoch metric is authoritative for the drawer so a delayed list summary cannot incorrectly display “pending”.

### Reference Bands

Quality bands are explicitly labeled “experience reference”, never pass/fail gates:

- mAP50: below 0.30 starting/weak, 0.30-0.50 preliminary, 0.50-0.70 good, above 0.70 strong.
- mAP50-95: below 0.20 weak, 0.20-0.40 preliminary, 0.40-0.60 good, above 0.60 strong.
- Precision and recall: below 0.50 low, 0.50-0.75 medium, above 0.75 good.
- Loss has no universal absolute range. Only its within-run trend and train/validation relationship are interpreted.

### Health Diagnosis

The browser derives cautious observations with visible evidence:

- Fewer than three usable validation epochs: collecting data.
- Recent quality improvement without sustained validation-loss deterioration: healthy.
- Precision/recall gap above 0.20, volatile values, or slowing improvement: observe.
- Overfitting risk only when recent training loss declines, validation loss rises, and quality does not improve.

No single noisy epoch produces an overfitting warning. Diagnostic copy explains the measured evidence and remains advisory.

### Charts

Add latest/best summaries, all/recent-20 range control, clearer Chinese tooltips, per-series visibility controls, and a best-epoch marker. Preserve the existing loss and quality charts and mask/box selector.

## Safety

Frontend source edits may cause Vite hot module replacement in the browser but do not restart or signal the Python process. Verification while training is active is limited to focused frontend tests and static type checks only when resource usage is acceptable; a full production build is deferred if it could contend for memory.

## Acceptance Criteria

- An available epoch metric never shows as pending because the list summary is stale.
- Every quality number shows a plain-language meaning and an explicitly non-binding reference band.
- Loss is never graded by a universal numeric threshold.
- Health status provides evidence and handles short histories safely.
- Detection and segmentation histories both work.
- Mobile layouts remain readable without horizontal overflow.
- No backend or runtime-training file changes.
