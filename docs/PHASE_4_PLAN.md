# Phase 4: library export and import (0.5.7)

## Inspection and plan

Reuse AppEntry, LibraryService, path/repository/category/environment validation,
existing JSON metadata and desktop integration. No schema migration. Add a Qt-free
`core/library_transfer.py` for versioned JSON validation, export, preview and file
preparation; add a LibraryService registration method for validated configurations
including missing files. Add `ui/library_transfer_dialog.py` with worker progress,
cancellation, preview selection, collision choices and results. Settings actions
open it through MainWindow; reload the library after import.

Export only an explicit configuration allowlist, never global settings, tokens,
backup paths or cached installer assets. Embed bounded icon bytes, never import
arbitrary icon paths. Environment variables require opt-in on export and import.
Validate the complete file before any database writes; reject unsupported schemas,
malformed/oversized data, unsafe IDs and invalid field types. Normalize paths and
recognize duplicate files (including aliases/hard links). Existing entries are
never overwritten. Conflicting IDs require an explicit new-ID choice; matching
names alone are valid separate applications. Missing files remain reconnectable.

Use background workers for JSON/icon/path reads and export writes, and one-record
preparation workers during import. Keep SQLite writes on the main thread. Recheck
conflicts before registration. Cancellation keeps completed imports and reports
remaining rows. Closing waits for active file work and cleans up prepared icons.
Export uses an atomic, private temporary file and protects known application,
icon and database files from replacement. Never execute imported applications.

Validation: offline round-trip and adversarial schema tests, conflict/missing-file
and race tests, cancellation/thread ownership/GUI routing tests, focused and full
regression suites, source selftest and light/dark layout inspection. Preserve Phase
3 changes and all existing AppImages. Version stays 0.5.7 at the user's request;
extend only its existing public release notes. No build or publication authorized.

## Implementation

The versioned envelope uses `format: appforge-library`, schema version 1 and an
applications list. Validation completes before preview/registration; 32 MiB file,
10,000 record and 10 MiB icon limits bound work and memory. JSON duplicate keys,
unknown fields, malformed types, unsafe IDs and unsupported schemas are rejected.
Export is atomic, preserves an existing file on failure/cancellation, and uses
0600 permissions. An appended .json destination also requires replacement approval
if that resulting path already exists.

Preview checks normalized paths, available file identities and supported formats.
Available symlink aliases/hard links are deduplicated. Missing/unavailable paths
can be imported; directories and mismatched existing file formats cannot. IDs are
preserved when unused. The explicit new-ID option handles collisions without
changing existing records or launchers; identical display names are allowed.

Workers prepare icon files with generated names inside the icon store; imported
icon paths are never accepted. Main-thread LibraryService registration validates
again and checks both immediate ID/path conflicts and the worker's full ID/path
snapshot, rejecting concurrent changes. Launcher failures keep the configuration
and produce a warning. Imported update/backup state is empty; future update checks
and existing local backup reconciliation supply fresh information. Inaccessible
paths now safely produce the library's missing/unavailable card state even on
Python versions whose Path.exists can raise permission errors.

Closing/cancelling waits for active work before finishing the dialog. An uncommitted
row's prepared icon is removed. Completed rows are retained and remaining rows
are reported; stop/cancel never rolls back or deletes existing application files.

## Validation

- **59 transfer tests passed** in `tests/test_library_transfer.py`: full configuration
  and icon round-trip, environment opt-ins, credential/runtime-state exclusion,
  complete-file validation, malformed/unsupported documents, duplicate JSON keys,
  limits, atomic writes, protected export destinations, missing-file reconnection,
  path/alias/hard-link/ID/name conflicts, changed-file and concurrent-library races,
  schema compatibility and database reopen, launcher failure, inaccessible files,
  no application execution, Settings routing, selective imports, worker/main-thread
  ownership, cancellation, pending-icon cleanup, and overwrite approval after
  appending the JSON extension.
- **237 focused tests passed**, combining transfer, release notes, details,
  self-hosted sources, discovery, backups, GUI regressions, publishing, menu
  environment variables and desktop integration.
- Full suite: **327 passed, 3 failed, 31 setup errors; no skips**. The failures are
  the same recorded injected-client expectation in `test_phase5.py`, its socket
  executable-installer test, and the socket single-instance test in `test_v053.py`.
  All setup errors occur while appimagetool builds shared fixtures. Phase 3's
  baseline was 268 passed with these same 3 failures and 31 setup errors.
- Source `PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m appforge --selftest`:
  **passed**. `git diff --check`: **passed**.
- Settings, export and import layouts rendered and visually inspected in light
  and dark themes. Long locations/statuses use tooltips; status columns can be
  resized. The standalone screenshot harness needed explicit Qt object teardown
  to avoid a shutdown crash; rerunning with orderly teardown completed normally.

## Changed files for Phase 4

- New service: `src/appforge/core/library_transfer.py`.
- Service integration: `src/appforge/core/library.py`.
- New UI: `src/appforge/ui/library_transfer_dialog.py`.
- Entry points: `src/appforge/ui/settings_dialog.py`, `src/appforge/ui/main_window.py`.
- New tests: `tests/test_library_transfer.py`.
- Documentation: `README.md`, `docs/LIBRARY_TRANSFER.md`, this plan and the local-only
  `roadmap.md`. Extended only `releases/RELEASE_NOTES_v0.5.7.md`, preserving its
  Phase 3 content and all previous releases' notes.

## 0.5.7 release preparation

Previous release source: **0.5.6**, commit `7944d72`. Confirmed prepared version:
**0.5.7**, combining the release-notes viewer and library export/import. Active
version declarations, README, roadmap, notes heading and selected binary filename
agree. Verified changes are documented in `releases/RELEASE_NOTES_v0.5.7.md`;
no release date was added. README and the transfer guide match the implemented
workflows. Changed files for both phases are listed here and in `PHASE_3_PLAN.md`.

The user reported **manual testing passed** after Phase 4 and requested preparation
of release 0.5.7. The sole matching local binary is a regular, non-symlink file:

- Asset: `dist/AppForge-0.5.7-x86_64.AppImage`
- Size: **84,584,952 bytes**
- SHA-256: `61491e172f3e30d524038517e8e2d14c0cec2ddf93613cc4c1e8d64a9304c96d`

This records the user's manual-test report and the current binary's identity;
it does not claim automated verification of its build provenance. No provenance
sidecar was supplied or required. The binary was not executed, built, renamed or
modified during preparation. Source code was not changed during preparation, so
these documentation/status updates do not require a new binary.

Fresh preparation checks:

- Focused suite: **237 passed**.
- Full suite: **327 passed, 3 failed, 31 setup errors; no skips**. The same
  previously documented provider expectation, restricted socket tests and
  appimagetool fixture errors remain; the complete suite is not passing here.
- Source offscreen `--selftest`: **passed**.
- `git diff --check`: **passed**.
- `./scripts/publish.sh release --dry-run`: **passed**. Local asset/version/notes
  checks and approved-path review completed without staging, fetching, committing,
  pushing or contacting GitHub. Offline checks do not verify remote availability
  or replace final publishing approval.
- Repository identity: `/home/thilen/appforge`, branch `main`, upstream
  `origin/main`, origin `https://github.com/Thilen03/AppForge.git`.

Release preparation is complete locally with the automated-test limitations above.
The user reports the matching version manually tested; no rebuild is requested.
Git metadata remains read-only here. No commit, push, tag or upload was performed.
Publication remains a separate action through `./scripts/publish.sh release` in
the user's normal Linux terminal, with remote preflights and its PUSH/RELEASE
confirmations. Phase 5 has not been started.
