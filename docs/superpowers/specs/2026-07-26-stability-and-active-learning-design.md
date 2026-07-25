# TrainForge 0.2.6 Stability Acceptance and 0.3.0 Active Learning Design

## Status

Approved design for two sequential releases:

1. `0.2.6` proves that the existing single-node platform can run, recover, and be operated safely over long periods.
2. `0.3.0` builds a traceable data-improvement loop on top of the accepted `0.2.6` baseline.

The releases must remain separate commits and tags. Development of `0.3.0` starts only after the complete `0.2.6` acceptance suite passes and `v0.2.6` is pushed.

## Goals

### 0.2.6

- Replace deprecated FastAPI startup and shutdown hooks with one lifespan boundary.
- Expose an operator-readable health snapshot for API, host memory, disk, GPU, database, and active work.
- Provide verified SQLite online backup without replacing the active database.
- Exercise API restart, abandoned jobs, expired leases, and failed subprocesses through fault-injection tests.
- Provide short CI acceptance and opt-in 8-to-24-hour soak execution.
- Remove known frontend runtime warnings and reduce large initial JavaScript chunks.

### 0.3.0

- Compare immutable dataset releases using content and annotation evidence.
- Identify and review low-confidence, false-positive, false-negative, and otherwise difficult inference samples.
- Return selected original media to an existing task and batch as review candidates.
- Compare training experiments and model artifacts using consistent metrics and resource evidence.
- Generate explainable training recommendations from task, dataset, hardware, and failure history.
- Benchmark PT and ONNX artifacts using comparable accuracy and runtime measurements.

## Non-goals

- Authentication, authorization, enterprise tenancy, Redis, remote workers, and distributed scheduling.
- Replacing SQLite with PostgreSQL in these releases.
- Adding a second training engine or a non-YOLO model family.
- Automatically labeling returned samples or automatically publishing a dataset release.
- Automatically deleting databases, datasets, annotations, model weights, or retained training outputs.

## Release 0.2.6 Architecture

### Application lifespan

FastAPI lifespan owns startup recovery and shutdown cleanup. Startup performs bounded maintenance only: recover abandoned background-job state, purge expired job metadata, verify that the registry can be opened, and start periodic health sampling. Shutdown stops owned sampler threads and executor resources without terminating unrelated operating-system processes.

The lifespan implementation must remain compatible with `TestClient` and the existing `create_app` dependency injection points.

### Operational health snapshot

A health service produces a point-in-time structured snapshot containing:

- API process RSS and optional process CPU usage;
- host physical and committed memory where the platform exposes them;
- storage capacity, free bytes, and free percentage;
- optional CUDA device name, free/used memory, and utilization when readable;
- SQLite integrity status and WAL size;
- counts of active training, inference, background, and heavy operations;
- sampling timestamp and partial-data warnings.

Unavailable metrics are represented as unavailable evidence, not zero. Metric collection must use short timeouts and must not block health checks or training.

The existing lightweight `/api/health` contract remains compatible. A separate detailed endpoint returns the operational snapshot so container health checks do not become dependent on GPU tools or expensive probes.

### SQLite backup and verification

The backup service uses SQLite's online backup API against the live registry. It writes to a staging filename in the configured backup directory, runs `PRAGMA integrity_check` against the staged copy, then atomically renames it to a timestamped backup.

Safety requirements:

- never close, overwrite, rename, or replace the live `factory.db`;
- never restore automatically;
- never include database files in deployment packages or Git;
- serialize backup jobs through the heavy-operation lease;
- enforce a configurable retention count only inside the dedicated backup directory;
- return file size, checksum, creation time, and integrity result.

Restore remains an explicit offline operator procedure documented in the help center.

### Stability acceptance runner

One command runs a bounded acceptance scenario using temporary storage:

1. create and query registry data;
2. start and recover a background job;
3. acquire, expire, and reclaim a heavy-operation lease;
4. execute simulated training and inference lifecycle transitions;
5. create and verify a database backup;
6. sample health repeatedly and assert bounded resource growth;
7. produce a JSON and Markdown report.

CI runs a short mode. Long mode is explicitly enabled by duration and uses a temporary or operator-selected test root. The runner refuses to use a directory containing the production marker or the configured production storage root.

### Frontend stability work

- Correct the known Ant Design `Descriptions` column-span mismatch.
- Preserve route-level lazy loading and split large vendor groups deliberately.
- Keep training, annotation, and inference state local to their existing route boundaries.
- Add rendering and navigation tests for lazy-loaded chunks.
- Treat chunk-size reductions as performance work only; no workflow redesign belongs in `0.2.6`.

## Release 0.3.0 Architecture

### Dataset release comparison

A comparison service reads two immutable release manifests and returns:

- added, removed, and content-identical images;
- changed, added, removed, and empty labels;
- per-class annotation-count deltas;
- split distribution changes;
- duplicate and cross-split leakage changes;
- source-group distribution changes when provenance exists.

Comparison results are generated artifacts keyed by both release IDs and their checksums. They do not mutate either release.

### Difficult-sample review

Inference results gain normalized sample evidence sufficient to query by model, task, confidence range, predicted class, run, and review disposition. Review dispositions are `unreviewed`, `correct`, `false_positive`, `false_negative`, and `difficult`.

False negatives require the reviewer to mark a sample and optionally select the missing class; the system must not infer a false negative solely from absent detections.

### Active-learning return flow

The return operation accepts reviewed inference sample IDs, a destination task, and an existing destination batch.

Data flow:

```text
Inference sample
  -> resolve managed original source
  -> validate task compatibility
  -> SHA-256 deduplicate within destination batch
  -> copy through operation staging
  -> create FrameAsset(status="candidate")
  -> record provenance to inference run, sample, and model
  -> commit files, records, and manifest atomically
```

Only the unmodified source image may be returned. Annotated overlays, thumbnails, rendered masks, videos with drawings, and temporary upload paths are rejected as training sources. If the original cannot be resolved, the UI explains why the sample cannot be returned.

The operation is idempotent. Repeating the same request returns the existing frame mapping instead of creating another managed file. Returned frames always enter `candidate`; they must pass selection, annotation, and review before release.

### Experiment comparison

The experiment comparison view accepts two to four completed or terminal training runs and displays:

- dataset release and content identity;
- base model, image size, batch, optimizer, patience, augmentation, and selected classes;
- best epoch and terminal epoch;
- box/mask precision, recall, mAP50, and mAP50-95 where available;
- runtime, peak host/GPU memory, failure diagnosis, and artifact size;
- per-class differences and an explicit warning when runs are not directly comparable.

The service reports evidence and differences; it does not declare a universal winner when datasets or test splits differ.

### Explainable recommendations

Recommendations are deterministic rules, not an opaque model. Inputs include task type, sample count, image dimensions, class balance, available GPU memory, previous resource failures, and prior run metrics.

Every recommendation includes the proposed value, observed evidence, reason, confidence, and safety bound. Applying recommendations populates the training form but never starts training automatically.

### Model benchmark

Benchmarks are immutable runs associated with a model artifact and a fixed sample manifest. PT and ONNX runs capture environment, warm-up count, measured iterations, preprocessing policy, latency percentiles, throughput, peak memory, artifact size, and available task metrics.

The UI marks comparisons invalid when sample manifests or preprocessing settings differ.

## Data Model Evolution

All schema changes are additive migrations. Existing business tables and rows are preserved.

Expected new concepts include:

- operational health samples or bounded report artifacts;
- database backup metadata;
- inference sample review disposition;
- active-learning return provenance and idempotency key;
- generated dataset-comparison artifacts;
- benchmark run metadata.

Large metrics, reports, and media remain managed files with checksums; SQLite stores their identity, status, and paths. Migrations must be rerunnable and tested against a copy of the previous-version schema.

## Error Handling

- Partial platform metrics produce warnings and a usable partial snapshot.
- Backup integrity failure deletes only the staged backup and leaves the live database untouched.
- Stability acceptance failure retains its isolated report directory for diagnosis.
- Active-learning staging failure removes staged files and creates no frame records.
- Missing original inference media blocks return while leaving review disposition intact.
- Dataset comparison detects missing or checksum-mismatched release files and reports a non-mutating validation error.
- Benchmark cancellation terminates only the verified owned subprocess and retains completed evidence.

## Testing Strategy

### 0.2.6 release gate

- Unit tests for lifespan services, partial health evidence, backup retention, and integrity failure.
- Integration tests for restart recovery, lease expiry, subprocess reconciliation, and backup API behavior.
- Short stability acceptance in CI using temporary storage.
- Complete backend tests, complete frontend tests, and production frontend build.
- Manual long soak report retained outside Git before tagging `v0.2.6`.

### 0.3.0 release gate

- Unit tests for comparison math, review transitions, recommendations, and benchmark comparability.
- Integration tests proving active-learning idempotency, provenance, atomic rollback, and overlay rejection.
- End-to-end test covering inference review through candidate return, annotation, new release, and experiment creation.
- Migration tests beginning from a `0.2.6` schema fixture containing representative relationships but no business data.
- Complete backend tests, complete frontend tests, production build, and data-safety diff scan before tagging `v0.3.0`.

## Deployment and Data Safety

Deployment remains source/image replacement with mounted runtime directories preserved. Neither release package may contain or overwrite SQLite files, data roots, task-specific runtime configuration, model roots, environment files, logs, or generated reports.

Before each cloud update, the deployment workflow creates and verifies an online SQLite backup. This is a precaution, not a migration input. Additive migrations run against the mounted live registry during API startup and must not rewrite existing media paths or class identities.

## Delivery Sequence

1. Write and approve the `0.2.6` implementation plan.
2. Implement `0.2.6` with test-first checkpoints.
3. Run complete automated verification and the short acceptance runner.
4. Commit, tag, and push `v0.2.6` atomically.
5. Write the `0.3.0` implementation plan against the pushed `0.2.6` baseline.
6. Implement the data comparison, review, return, experiment, recommendation, and benchmark slices.
7. Run complete automated and end-to-end verification.
8. Commit, tag, and push `v0.3.0` atomically.

