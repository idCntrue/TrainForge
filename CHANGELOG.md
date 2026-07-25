# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

## 0.2.2 - 2026-07-26

- Reconcile training and inference subprocesses that exit without a valid terminal event or completed result, preventing permanently active runs.
- Protect restart-time cancellation with persisted process tokens and live command-line identity checks so reused PIDs cannot terminate unrelated processes.
- Release completed subprocess references promptly to avoid accumulating process handles during long-running desktop and server sessions.
- Consume training and inference JSONL progress incrementally with durable byte cursors, partial-line safety, and file-replacement recovery.
- Replace overlapping interval polling with abortable, completion-driven polling, background-tab throttling, and bounded retry backoff.
- Unify backend, frontend, API, and bilingual documentation version metadata at 0.2.2.

## 0.2.0 - 2026-07-23

- Add portable published-model release bundles containing validated PT/ONNX weights, ordered class files, deployment metadata, and SHA-256 checksums.
- Allow one completed training run to register multiple immutable model versions while preventing duplicate model name/version pairs.
- Add model-gate history management with independent ONNX artifacts, diagnostics, safe deletion, and automatic fallback to a previous valid gate run.
- Add imported PT/ONNX inspection and reliable batch inference behavior for externally supplied models.
- Add dataset-storage reconciliation and guarded repair for database/filesystem drift.
- Redesign the model detail drawer, inference controls, training overview, and responsive mobile layouts for dense operational workflows.
- Add Windows training-memory safeguards, resource cleanup controls, and clearer failure diagnostics without modifying managed datasets or cloud runtime data.

## 0.1.1 - 2026-07-20

- Add a four-step training creation wizard with explicit basic settings, strategy controls, early stopping, augmentation parameters, and a final configuration review.
- Diagnose OpenCV and DataLoader host-memory exhaustion correctly, and use a zero-worker GPU loading policy by default to reduce Windows RAM pressure.
- Expose persisted model-gate diagnostics and provide plain-language failure evidence in the model center.
- Add a complete searchable native-annotation guide covering drawing, object selection, class changes, SAM2, review, appended images, and dataset publication.
- Add an adaptive mobile and tablet information architecture with fixed bottom navigation, card-based records, safe-area support, and touch-oriented annotation layouts.
- Add a guarded cloud-to-Windows data synchronization script that verifies SQLite, backs up the local database, migrates storage paths, and never replaces the production cloud database.
- Harden deployment packaging and one-command updates so runtime data, models, `.env`, task-specific configuration, and SQLite databases remain outside release archives.
- Expand bilingual documentation and reviewed desktop/mobile screenshots without publishing customer media, deployment addresses, credentials, or runtime data.
