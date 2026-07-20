# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

## 0.1.1 - 2026-07-20

- Add a four-step training creation wizard with explicit basic settings, strategy controls, early stopping, augmentation parameters, and a final configuration review.
- Diagnose OpenCV and DataLoader host-memory exhaustion correctly, and use a zero-worker GPU loading policy by default to reduce Windows RAM pressure.
- Expose persisted model-gate diagnostics and provide plain-language failure evidence in the model center.
- Add a complete searchable native-annotation guide covering drawing, object selection, class changes, SAM2, review, appended images, and dataset publication.
- Add an adaptive mobile and tablet information architecture with fixed bottom navigation, card-based records, safe-area support, and touch-oriented annotation layouts.
- Add a guarded cloud-to-Windows data synchronization script that verifies SQLite, backs up the local database, migrates storage paths, and never replaces the production cloud database.
- Harden deployment packaging and one-command updates so runtime data, models, `.env`, task-specific configuration, and SQLite databases remain outside release archives.
- Expand bilingual documentation and reviewed desktop/mobile screenshots without publishing customer media, deployment addresses, credentials, or runtime data.
