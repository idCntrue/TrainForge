# Inference Result Viewer Design

## Scope

Replace the vertically stacked batch-image results on `/inference` with a controlled result viewer. This is a frontend presentation change: inference submission, backend execution, result persistence, model selection, history, and artifact files remain unchanged.

## Goals

- Show one full-size image result at a time.
- Allow previous/next navigation without moving the page vertically.
- Show annotated result thumbnails in one horizontally scrollable strip below the main image.
- Keep the selected thumbnail visible and visually distinct.
- Show the active position, filename, detection count, inference duration, mask toggle, and artifact action in one stable toolbar.
- Preserve the current single-image and video workflows.
- Support mouse, keyboard, touch, desktop, and mobile layouts.

## Interaction

### Batch images

The result panel displays the active annotated result image. A counter shows `current / total`. Previous and next icon buttons move by one result and are disabled at the ends. The left and right arrow keys perform the same navigation while the viewer has focus. On touch devices, a deliberate horizontal swipe on the main media area changes the active result.

The thumbnail rail appears below the active result. It is a single non-wrapping row with horizontal overflow. Each thumbnail uses the annotated result media, includes a compact ordinal label, and exposes its filename through accessible text and a tooltip. Selecting a thumbnail updates the main image and metadata. When navigation changes the active result, the selected thumbnail scrolls into view.

### Single image

The same viewer renders the single result, but hides the counter navigation controls and thumbnail rail.

### Video

The existing video player remains. Image navigation, image thumbnails, structured-mask switching, and swipe navigation do not appear.

### Structured masks

The existing structured-mask switch applies only to the active image. If enabled and the active result contains polygons, the viewer shows the source image with the structured polygon overlay. Otherwise it shows the annotated media artifact. Changing results preserves the switch state.

## Component Boundaries

- `InferencePage` continues to own inference form state, run selection, history, polling, cancellation, and deletion.
- A result-viewer component owns the active result index, navigation, focus/keyboard handling, touch gesture handling, thumbnail scrolling, and active-result presentation.
- Pure presentation helpers determine whether navigation is available and clamp/reset an active index when the result collection changes.

The active index resets to zero when a different inference run is opened or a newly completed run replaces the current run. It is clamped if the current result list shrinks during refresh.

## Layout

The viewer has four stable bands:

1. Header: title, status, structured-mask switch, and run cancellation when applicable.
2. Media stage: one centered image or video with bounded responsive dimensions.
3. Active-result toolbar: filename, result summary, inference duration, counter, navigation, and artifact action.
4. Thumbnail rail: batch-image results only.

The media stage keeps the current aspect-ratio-preserving behavior. Controls do not overlay the image, so boxes and masks remain unobstructed. The thumbnail rail is contained within the result panel and does not create page-level horizontal overflow.

On mobile, metadata can wrap onto two lines, icon controls retain stable touch targets, the thumbnail rail remains horizontal, and the main image supports touch swiping. No bottom-fixed control is introduced.

## Accessibility

- Previous and next controls use buttons with Chinese accessible labels and tooltips.
- The result viewer is keyboard-focusable and documents its current item through an accessible label.
- Active thumbnails expose `aria-current` and a visible non-color-only selection treatment.
- Images retain descriptive alternative text based on source filename.
- Motion is limited to native scrolling; no automatic carousel playback is used.

## Performance

Only the active result creates a full-size preview node. Thumbnail images use lazy loading and the existing annotated artifact URLs. This phase does not add a backend thumbnail endpoint. The component boundary allows optimized thumbnail URLs to be introduced later without changing viewer behavior.

## Error And Empty States

- A completed run with no results continues to show the existing empty state.
- A result without previewable media shows the existing per-result empty state while retaining its metadata.
- Failed, cancelled, interrupted, queued, and running run states keep their existing behavior.
- A failed thumbnail does not prevent navigation or the main result from rendering.

## Verification

- Unit tests cover index clamping, reset behavior, navigation availability, and preview-kind behavior.
- Component tests cover thumbnail selection, previous/next controls, keyboard navigation, mask behavior for the active item, and hiding batch controls for image/video modes.
- Layout tests verify the horizontal non-wrapping thumbnail rail and mobile constraints.
- The frontend test suite and production build must pass.

## Non-Goals

- No backend inference API changes.
- No database or artifact migration.
- No result reordering, comparison mode, bulk download, or slideshow autoplay.
- No generated backend thumbnail files in this iteration.
