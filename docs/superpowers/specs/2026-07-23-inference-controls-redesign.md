# Inference Controls Redesign

## Goal

Make the `/inference` configuration panel faster to scan and shorter to operate without changing inference APIs, model records, uploaded media, history, or result presentation.

## Design

The panel uses three stable bands:

1. A compact media-mode segmented control.
2. A grouped form with model, runtime, input, and threshold sections.
3. A visually stable primary submit bar.

Model source and task remain visible because they determine all downstream choices. Existing-model selection is the primary imported-model workflow. Importing a new PT/ONNX file moves to a dedicated modal opened beside the existing-model selector, so the main form no longer shows an empty model-name input, file picker, and disabled upload button at all times.

Candidate and imported sources show one compact warning line instead of a large descriptive alert. Runtime remains a segmented control. The media drop zone is shorter and reports the selected file count. The confidence control shows its current numeric value and a short low/high trade-off hint.

The submit bar remains at the bottom of the panel and contains one full-width primary action. Upload progress appears directly above it. Mobile uses the same information architecture, with two-column field groups collapsing to one column and all controls retaining touch-safe heights.

## State And Error Handling

The existing inference form remains the source of truth for task, model, runtime, and confidence. The import modal uses a separate form so unfinished import data cannot affect inference validation. Successful import closes and resets the modal, selects the new managed model, and sets its supported runtime. Import failure leaves the modal open with the selected file intact.

Switching task or model source chooses the first compatible model and clears incompatible selections. Switching media mode clears selected media as before.

## Verification

- Source and CSS contract tests cover the grouped panel, compact warning, modal import flow, threshold value, selected-media status, and responsive layout.
- Existing inference result, API mapping, and frontend suites remain green.
- TypeScript and the production Vite build pass.

## Non-Goals

- No inference API or database change.
- No multi-step wizard.
- No model deletion or editing inside the inference page.
- No change to inference results or history behavior.
