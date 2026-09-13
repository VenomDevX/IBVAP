# IBVAP Remediation and Product Completion Plan

Status: In progress

Current verified runtime (2026-09-13): frontend is served on port 3001 and
proxies API/media/WebSocket traffic to the backend on port 8002. The seven-camera
pipeline is running with `IBVAP_PERSIST_EVENTS=false` for a safe demonstration;
the snapshot count remained fixed at 27,634 during the soak. Existing evidence
uses 5,715.6 MiB, above the new 2,048 MiB capture ceiling, so new snapshot capture
is paused until evidence is archived or retention is explicitly approved.

This plan converts the September 2026 full-stack audit into ordered, testable
implementation phases. A phase is complete only after its acceptance checks pass.

## Phase 0 — Contain unsafe runtime behaviour

- [x] Stop duplicate event and evidence generation.
- [x] Add per-camera persistence quotas and incident-level deduplication.
- [x] Make snapshot capture atomic and storage-budget aware.
- [x] Add a non-persistent demo mode.
- [x] Separate API liveness from AI/camera readiness.
- [x] Show truthful backend, pipeline, camera, model and storage status in the UI.

Acceptance: a controlled multi-camera soak test cannot exceed configured event,
alert or snapshot budgets, and an unavailable pipeline never appears "online".

## Phase 1 — Data integrity and lifecycle

- [x] Resolve all runtime paths from one configured data root.
- [x] Enable SQLite foreign keys and add missing indexes/relationships.
- [x] Add versioned, idempotent schema migration support.
- [x] Enforce snapshot retention independently of alert-row retention.
- [x] Add database backup, integrity-check and storage-health commands.
- [x] Remove inconsistent in-memory versus database statistics.

Acceptance: migrations work on both a fresh and existing database; retention dry
run reports every affected row/file; dashboard totals survive process restarts.

## Phase 2 — Incident operations and data access

- [x] Add an incident lifecycle: open, acknowledged, investigating, resolved,
      false positive and reopened.
- [x] Add assignee, notes, disposition, timestamps and immutable audit entries.
- [ ] Group repeated events under one incident.
- [x] Add server-side pagination, sorting, date range and complete filters.
- [ ] Add safe bulk actions and complete filtered exports.

Acceptance: an operator can find, own, investigate and resolve an incident without
losing its evidence or history, including after a restart.

## Phase 3 — Camera and zone administration

- [x] Add camera create/update/delete, enable/disable, test and restart APIs.
- [x] Make the database the runtime source of truth after initial YAML import.
- [x] Add camera location, stream and model configuration UI.
- [x] Add visual polygon/line drawing, editing and enable/disable for zones.
- [x] Enforce role and camera scope consistently in navigation and actions.

Acceptance: an administrator can configure a new camera and restricted zone from
the UI and see the pipeline reflect the change without editing YAML.

## Phase 4 — Operator-focused frontend

- [ ] Redesign the dashboard around the highest-priority unresolved incident.
- [ ] Add synchronized incident, camera, map and evidence selection.
- [x] Add configurable multi-view tiles, fullscreen and paging.
- [x] Improve typography, hierarchy, responsive layouts and empty/degraded states.
- [x] Meet keyboard, focus, contrast and screen-reader accessibility basics.
- [x] Replace full bearer query-string credentials with scoped, short-lived media tickets.

Acceptance: core monitoring and incident resolution are usable by keyboard, on a
laptop-sized display, and during partial backend/camera failure.

## Phase 5 — Models, reporting and operations

- [x] Expose actual model/dependency/device status and initialization errors.
- [x] Disable unsupported features explicitly instead of silently using mock data.
- [ ] Produce detector, tracker, ANPR and alert-quality evaluation artifacts.
- [x] Generate real PDF reports and safely escaped CSV downloads.
- [ ] Add metrics, structured operational logs, storage alarms and notification
      delivery/retry status.
- [ ] Add deployment backup/restore, retention scheduling and offline map support.

Acceptance: UI and documentation agree with runtime model capability; published
quality metrics are reproducible; an operator can diagnose resource exhaustion.

## Phase 6 — Verification and release

- [ ] Add frontend unit, accessibility and end-to-end tests.
- [ ] Run the full backend suite, frontend typecheck/lint/build and security checks.
- [ ] Run restart, degraded-mode and bounded-storage soak tests.
- [ ] Update PRD/TRD/status/deployment documentation to match delivered behaviour.

Acceptance: all required CI checks pass and the release checklist contains no
known P0/P1 defect.
