# Phase 5 storage manager

## Inspection and implementation plan

Reuse Phase 0 preparation, AppEntry snapshots, BackupService retention and backup
folder conventions, the existing theme, and QRunnable signals. Add a Qt-free
storage snapshot/cleanup service and an asynchronous storage dialog reached from
the library. No schema migration or new dependency (paint the donut with QtGui).

Show total applications/backups, a donut breakdown, ranked app table with numeric
sorting and backup filtering, and selectable backup version/date/size rows.
Preview conservative reclaimable bytes and require confirmation. Offer selection
of backups beyond the existing retention limit without changing that setting;
explicit individual selection remains available as in the existing backup dialog.

Harden shared backup scanning/deletion: only the expected app directory, regular
non-symlink files, no symlink directory components, pinned directory descriptors,
identity rechecks, and protection for registered current files. Keep file work
in workers and SQLite writes on its owning thread. Retain incomplete results with
warnings, cancellation, manual refresh, stale-snapshot rejection and safe closure.
Logical file sizes include hard links; reclaimable savings exclude multiply linked
files. Filesystem races cannot provide an atomic compare-and-unlink on Linux;
pinned directories and immediate identity checks narrow that residual race.

Validate storage arithmetic, missing/inaccessible files, retention, adversarial
paths/symlinks, changed-file cleanup, partial failures, cancellation, thread ownership,
UI routing and both themes; run relevant regression tests, full suite and selftest.
Advance development version 0.5.7 to 0.5.8; preserve historical notes and dist files.

## Implemented files

- `core/storage.py`: read-only app/backup snapshots, logical totals, per-file
  identity and conservative savings, cancellation and selective cleanup results.
- `core/backups/files.py`: pinned no-follow directory traversal, expected-folder
  boundaries, regular-file/identity checks and protection of registered current files.
- `core/backups/service.py`: reuse those boundaries for listing, deletion and
  retention pruning; keep unavailable-folder records instead of clearing them.
- `ui/storage_dialog.py`: painted donut, totals/counts/leaders, ranked sortable
  applications, backup filter and selection, retention selection, confirmation,
  workers/progress/stop, stale-snapshot rejection and deferred close.
- `ui/main_window.py`, `ui/theme.py`: library entry point and themed table styling.
- `ui/backups_dialog.py`: report unavailable managed directories gracefully.
- `tests/test_storage.py`: 19 storage/safety/worker/UI regression cases.
- `README.md`, `docs/STORAGE.md`, `docs/DISCOVERY.md`, local `roadmap.md`,
  `pyproject.toml`, `src/appforge/__init__.py`, and public
  `releases/RELEASE_NOTES_v0.5.8.md`: usage, status and consistent current version.

No database schema change, migration, settings change or new dependency. Existing
release notes and all dist files were preserved. No build, commit or publication.
Git metadata remains read-only in this environment.

## Validation

- 19 storage tests passed: arithmetic/counts, missing files, read-only snapshots,
  retention selection/unlimited retention, numeric UI sorting/filtering,
  file/folder/ancestor symlinks, foreign folders, stale file identity, hard links,
  registered current-file protection, disappearing backups, permissions and partial
  cleanup, cancellation, confirmation/cancel, busy/concurrently changed records,
  worker/SQLite thread ownership, safe close, main-window routing and existing
  backup-dialog unavailable-folder handling.
- Focused regression suite: **256 passed** (storage, backups, details, transfer,
  release notes, discovery, GUI, publishing, menu environment, desktop and
  self-hosted updates).
- Full suite: **346 passed, 3 failed, 31 setup errors**, no skips. The same known
  failures remain: provider injected-client expectation in
  `test_phase5.py::test_checker_routes_by_provider_and_uses_injected_client`, socket
  restrictions in its executable installer test, and the single-instance test in
  `test_v053.py`. All 31 setup errors arise while building shared AppImage fixtures
  using appimagetool. Previous recorded full-suite baseline: 327 passed with the
  same failures/errors; 19 new cases pass. No test expectation was weakened.
- Offscreen application `--selftest`: **passed**. `git diff --check`: **passed**.
- Storage dialog rendered and visually inspected in light and dark themes;
  backup date/size widths adjusted after inspection. Native desktop interaction
  and a matching 0.5.8 AppImage still require the user's build/manual testing.

Phase 5 source is implemented with these verification limits. Phase 6 remains
planned. Publication and matching AppImage approval are separate tasks.

## 0.5.8 button styling follow-up

At the user's request, Check for updates, Discover apps and Storage now reuse the
primary blue button style already used by Add Application, matching the Settings
gear's background and foreground colours. Version remains 0.5.8. Updated the
matching release notes. The user reports storage works and its design looks good;
this does not identify or approve a specific rebuilt AppImage with this follow-up.

Validation: 23 GUI/storage tests passed; source offscreen selftest and whitespace
checks passed. Library layouts with all three buttons visible were rendered and
visually inspected in both light and dark themes. Existing AppImages untouched.

The 0.5.8 styling follow-up also shares the header's 10-pixel spacing for the
Check for updates / Discover apps / Storage row. Rendered geometry confirms both
inter-button gaps exactly match Add Application / Settings (10 pixels) in light
and dark themes. Both layouts were visually inspected. All 23 GUI/storage tests,
the source selftest and whitespace checks passed after this spacing adjustment.

## 0.5.8 release preparation

Previous released source: **0.5.7**, commit `11f0053`. User-confirmed prepared
version: **0.5.8**, including Phase 5 storage, backup safeguards, primary blue
library buttons and matching 10-pixel gaps. Version declarations in pyproject,
package init, README and roadmap agree with the release-notes heading and selected
asset filename. No new version increment or release date was added.

Reviewed the changes against the previous release, source, tests and visible
user feedback. Public notes contain only implemented features and limitations.
README now links the 0.5.8 notes. Removed the stale public note saying the AppImage
still needs building: a matching file is now present, although its build source
and final manual-test approval have not been independently established. This
preparation changes only README, the 0.5.8 notes, this plan and local roadmap status;
application source and every existing binary remain untouched.

Selected local asset (regular, non-symlink, nonempty):

- `dist/AppForge-0.5.8-x86_64.AppImage`
- Size: **84,609,528 bytes**
- SHA-256: `44ec01e730dcea1d66d7210271302ac1259dc8a222cadd0e8bd61c2b201fbb39`

No provenance sidecar was supplied or required. The user reports the storage
works and likes the design/colours. That does not identify this exact file or
confirm that it was built from the final source including the spacing change.
Before publishing, the user must confirm building from that prepared source and
manually testing this exact binary. Automated checks do not supply that approval.
If the current asset predates the final source, the user must build/test a matching
one themselves. No binary was executed, rebuilt, renamed or otherwise changed.

Fresh preparation checks:

- Focused regression suite: **256 passed**.
- Full suite: **346 passed, 3 failed, 31 setup errors**, no skips. Failure names
  and reasons agree with the limitations documented above (provider expectation,
  restricted sockets, and appimagetool fixture setup). The full suite is not passing.
- Offscreen source `--selftest`: **passed**.
- `git diff --check`: **passed**.
- `./scripts/publish.sh release --dry-run`: **passed**. It verified local
  asset/version/notes consistency and approved-path selection without fetching,
  staging, committing, pushing, networking or assuming manual testing approval.
  Remote authentication, tag/release availability and source publication remain
  unchecked offline.
- Repository identity verified: `/home/thilen/appforge`, `main`, upstream
  `origin/main`, origin `https://github.com/Thilen03/AppForge.git`.

Source preparation is complete with these verification limits. Source is ready
for the user's build/manual-test verification. Git metadata is read-only here;
no staging, commit, tag, push or upload was performed. Publication remains separate
through `./scripts/publish.sh release` in the user's normal Linux terminal, with
its remote checks and PUSH/RELEASE confirmations. Phase 6 remains planned.
