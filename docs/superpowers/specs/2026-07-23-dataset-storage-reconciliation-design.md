# Dataset Storage Reconciliation Design

## Goal

Add a safe reconciliation workflow to `/datasets` that diagnoses drift between SQLite dataset release records and managed release directories, then permits only validated, explicit repairs.

## Scope

The first version provides:

- A read-only scan of database releases and `dataset-releases/*/dataset-v*` directories.
- Statuses for healthy releases, missing directories, orphan directories, invalid manifests, checksum failures, and missing provenance.
- A single repair action that registers an orphan directory only after all metadata, foreign-key, path, schema, and checksum checks pass.
- A responsive dataset reconciliation drawer with summary counts, actionable findings, and refresh.

It does not copy files from cloud hosts, delete records or directories, overwrite existing releases, or modify valid release contents.

## Safety Model

The database and filesystem are not treated as interchangeable authorities. Scanning is read-only. Repair requests identify one normalized release path and one explicit action. Every managed path must resolve below `<storage_root>/dataset-releases`, symlinks are rejected, and database writes occur only after validation.

Database-only records cannot restore image bytes. They are reported as `missing_artifacts` with guidance to restore from DVC, backup, cloud sync, or republish from the annotation export.

Filesystem-only directories are reported as `orphan_directory`. Registration is allowed only when:

- Directory naming matches `dataset-releases/<task_id>/dataset-v<semantic-version>`.
- `manifest.yaml`, `data.yaml`, and `checksums.sha256` exist and parse successfully.
- Manifest task and version match the directory.
- The referenced task and annotation export exist and belong together.
- Dataset validation passes for the registered task contract.
- Every checksum entry is safe, exists, and matches, with no path traversal.
- The derived release ID, version, and release path do not conflict with existing records.

## Backend Design

Create `yolo_factory.datasets.reconciliation` with pure scanning and validation helpers plus a transactional `register_orphan_release` operation. The service returns serializable findings and does not depend on FastAPI.

Expose:

- `GET /api/dataset-releases/reconciliation` for a fresh read-only scan.
- `POST /api/dataset-releases/reconciliation/register` with `{ "release_path": "dataset-releases/..." }`.

The registration endpoint returns the created dataset release summary. Validation failures return `409` with a concrete reason; invalid paths return `422`.

## Finding Contract

Each finding contains:

- `key`, `release_id`, `release_path`, `task_id`, and `version` where known.
- `database_exists`, `directory_exists`, `manifest_valid`, and `checksums_valid`.
- `status`: `healthy`, `missing_artifacts`, `orphan_directory`, `invalid_manifest`, `checksum_failed`, `missing_provenance`, or `conflict`.
- `message` with the concrete diagnosis.
- `allowed_actions`, currently either empty or `register`.

## Frontend Design

Add a `检查存储一致性` action to the dataset-version panel. It opens a drawer rather than changing the table structure. The drawer shows summary metrics and a compact finding list grouped by severity. Healthy results remain visible but visually quiet; destructive actions are absent.

An orphan directory with `register` permission exposes `重新注册`. The confirmation dialog states that files are not copied or modified. After registration the app refreshes both the scan and dashboard data.

## Error Handling

- A failed scan leaves existing dataset data unchanged and displays the API detail.
- A failed registration leaves the directory and database unchanged.
- Concurrent registration is resolved by database uniqueness/primary-key checks and reported as a conflict.
- Missing files during a scan are findings, not server errors.

## Verification

Unit tests cover path containment, healthy/missing/orphan classifications, checksum verification, provenance rejection, and successful registration. API tests cover both endpoints. Frontend contract tests verify the reconciliation entry point, drawer, statuses, and repair action. The full Python and frontend suites plus the production frontend build must pass.
