# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

## 0.2.6-rc.1 - 2026-08-03

- Replace deprecated FastAPI startup/shutdown handlers with an application lifespan that owns recovery and bounded periodic cleanup threads.
- Add bounded detailed operational health evidence for process memory, host memory, storage, GPU, SQLite, and active work while preserving the compact health endpoint.
- Add guarded SQLite online backups with integrity checks, SHA-256 metadata, managed retention, and no automatic restore behavior.
- Add isolated short and eight-hour stability acceptance modes covering registry operations, restart recovery, lease reclaim, simulated training and inference, verified backup, and process-memory growth.
- Cover restart, expired-lease, and backup-write faults without modifying production storage.
- Remove the responsive Ant Design descriptions warning and split stable frontend vendor groups while keeping route-level lazy loading.
- Unify backend, frontend, API, deployment examples, and bilingual documentation version metadata at 0.2.6-rc.1.
- Publish as a release candidate after the complete automated suites, production build, 60-second isolated acceptance, and an operator-ended partial soak of about one hour; this does not claim the full eight-hour stability gate.

## 0.2.5 - 2026-07-26

- Persist background jobs in SQLite, recover interrupted work after API restarts, and coordinate heavy operations through expiring database leases.
- Add bounded model-gate execution with subprocess cancellation and a configurable timeout.
- Make video append operations atomic across managed files, frame records, video records, and batch manifests.
- Export portable native-annotation archives with images, labels, `classes.txt`, `data.yaml`, a source index, and verified SHA-256 metadata; reviewed empty annotations are retained as negative samples.
- Reject ZIP imports that exceed file-count, expanded-size, compression-ratio, or path-depth limits before extraction.
- Reduce SQLite lock contention with WAL, normal synchronous mode, a five-second busy timeout, and bounded list queries.
- Add compatible status/limit/offset filtering for training runs, inference runs, model versions, and background jobs.
- Cache unchanged dataset image hashes and decode results while continuing to revalidate labels and class statistics on every release.
- Unify backend, frontend, API, deployment examples, and bilingual documentation version metadata at 0.2.5.

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
