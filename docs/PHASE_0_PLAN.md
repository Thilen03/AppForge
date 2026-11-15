# Phase 0 inspection and implementation plan

Inspected for the 0.5.5 discovery update, 14 November 2026.

## Existing architecture

- `app.py` initializes SQLite, LibraryService, startup launcher repair, the Qt window,
  single-instance control and self-update restart handling.
- `core/database.py` applies append-only migrations using SQLite user_version. There
  are two migrations: application records and a global settings key/value table.
  AppEntry stores extensible per-app metadata and backup information as JSON.
- `core/formats` detects AppImages before generic ELF/shebang executables. Existing
  metadata readers inspect bytes and embedded SquashFS without executing files.
- `LibraryService` owns library writes, normalized paths, icon storage and desktop
  integration. The SQLite connection belongs to the main thread.
- Cards/dialogs use the shared theme. QRunnable workers emit Qt signals for network
  work; cancellation uses threading.Event. Check and installation pools are separate.
- Providers normalize GitHub/GitLab/Codeberg/custom-host releases. The installer
  validates downloads, optionally checks hashes, preserves backups and swaps files
  atomically. BackupService manages retention and reversible rollback.
- Tray functionality currently provides Open, Check and Quit. Settings and update
  notifications already persist. None of these workflows needs replacement.
- Tests include core, GUI, provider, installer, backup and desktop checks. Real
  AppImage fixtures require appimagetool. Packaging uses PyInstaller/appimagetool.

## Phase 1 plan

1. Add Qt-free discovery models/scanning and preference helpers in core/discovery.py.
   Scan explicit default/custom roots recursively without following symlinks; exclude
   managed backup folders, deduplicate by normalized path and device/inode, report
   errors, progress and cancellation, and reuse inspect_file.
2. Add a dedicated discovery dialog with configurable roots, a worker, preview table,
   checkboxes, select all/none, import selected/all, ignore, progress and cancellation.
   Keep DB writes on the UI thread, one candidate per event-loop turn. Require an
   explicit import confirmation and revalidate each candidate before registering it.
3. Add the entry point beside the library update controls; refresh the library after
   the dialog closes. Reuse LibraryService and its desktop integration preference.
4. Add scanner/import/GUI tests, run regression checks, update README/version/roadmap,
   and package only changed files plus versioned release notes.

No schema migration: discovery roots and ignored paths use the existing settings
store; old application records and preferences remain untouched. Risks include
filesystem races, restricted directories, huge directory trees and worker lifetime.
Use non-followed symlinks, identity checks, bounded progress reporting, cooperative
cancellation and deferred dialog closure until the worker finishes. Cancellation
cannot interrupt an individual metadata read already in progress.

## Later phases: likely components (not implemented in this update)

| Phase | Likely components |
| --- | --- |
| 2 Details | New details dialog; app_card/main_window actions; existing library/update/backup services |
| 3 Release notes | Release model and provider mappings; cached metadata; new async viewer |
| 4 Export/import | New validated JSON service/dialog; settings actions; library persistence |
| 5 Storage | New background size service/overview; BackupService cleanup reuse |
| 6 Enhanced tray | tray/main_window, settings, launch service, notification coordination |
| 7 Integration | Existing test modules plus feature tests and database upgrade fixtures |

## Update discovery repair plan (0.6.1)

Repair `core/updates/checker.py`, `assets.py`, `version.py`, `service.py` and
filename extraction; pass the installed path through the existing Qt check worker.
Reuse release/asset models, checksum readers and metadata settings. No database
migration. Preserve stable/prerelease preferences and numeric downgrade protection.
Use published hashes only when the exact asset is unambiguous, read installed files
on the worker, and explain that different bytes cannot establish version ordering.
Make saved asset patterns strict and architecture checks independent of scoring.
Validate unusual tags, title/filename fallbacks, rolling releases, hash matches and
mismatches, pattern persistence, architecture safety and existing installer safeguards
with deterministic provider fixtures, the regression suite and startup smoke test.

### Implementation and verification

Implemented the discovery repair above and confirmed 0.6.1 with the user.
Existing metadata stores the comparison method; no schema migration or dependencies
were added. The picker filters by registered format and host architecture. Single
updates and Update All explain checksum-based updates whose order is unknown.
Light/dark confirmation dialogs were rendered and inspected; text and buttons fit.
The worker now always emits a failed outcome for unexpected exceptions.

The system interpreter initially lacked PySquashfsImage, and fixture creation tried
to fetch a runtime over the restricted network. Use the already installed build
virtualenv dependencies and an extracted runtime from the local appimagetool for
offline test fixtures. This does not build or modify any distributable under dist.

Focused new regression coverage: 58 passed, including real AppImage replacement,
SHA-512 verification, checksum mismatch, truncation, invalid files and cancellation.
Startup smoke test: passed with the offscreen Qt platform. Live provider requests
and tests requiring local TCP/Unix sockets remain restricted in this environment.
No final application binary was built or manually tested, and nothing was published.

Final complete regression run with those local dependencies/runtime: **590 passed,
12 skipped, 1 existing Qt deprecation warning**. All skips explicitly report the
host's TCP/Unix socket restrictions. Final `git diff --check` passed. Source 0.6.1
is ready for the user to build and manually test as
`AppForge-0.6.1-x86_64.AppImage`; publication approval remains outstanding.

## Pre-release opt-in follow-up (kept in 0.6.1 by user confirmation)

The checker correctly excludes pre-releases by default, but the asset picker lists
files from an excluded nightly without offering to enable its channel. Add an
explicit per-app enable/stable-only menu action in app_card.py and connect it in
main_window.py. Reuse LibraryService's include_prereleases setting and existing
check worker. When choosing an excluded pre-release asset, ask to opt in before
saving either setting or pattern. Invalidate stale results on channel changes;
preserve paused/skipped controls and all other apps. No schema change. Test menu
and picker opt-in, decline/cancel, persistence, stable filtering and busy guards;
run update/GUI regressions, smoke test and inspect both themes.

### Pre-release follow-up verification

Focused update/UI regression run: **114 passed, 10 skipped** (restricted TCP
sockets). This includes 10 new tests for menu and asset-picker opt-in, cancellation,
stable-only transitions, persistence, busy guards, paused updates and isolation
from other apps. Startup offscreen self-test passed. Rendered and inspected the
new menu action and opt-in prompt in light and dark themes; labels/buttons fit.
The user's explicit preference keeps these changes in 0.6.1 and its existing public
notes. No database migration, distributable build or publication.

Final complete regression run after the pre-release follow-up: **600 passed,
12 skipped, 1 existing Qt deprecation warning**. Skips are the host's socket
restrictions. `git diff --check` passed. The revised 0.6.1 source is ready for the
user to rebuild and manually test; the previously tested binary does not contain
this follow-up until rebuilt. Git metadata remains read-only here.

## Download-and-add plan (0.6.1 by user confirmation)

Add a local/link chooser before the ordinary Add flow, bypassed for drag-and-drop
paths. Add core/downloads.py for provider discovery and exclusive new-file
publication, and ui/download_dialog.py for release/asset/destination selection.
Reuse discovery_roots, existing providers, candidate/architecture filters, format
inspection, and the installer's checksum/download validation pipeline. Network
and file work run in cancellable Qt workers; SQLite writes remain on the UI thread.
Open the existing Add form after downloading, prefilling source and release metadata
and preserving the asset variant and pre-release preference. No schema migration.
Never overwrite destination files, execute downloads, or remove completed downloads
when final registration is cancelled. Reject unsafe filenames and symlink folders;
recheck downloaded identity before registration. Test offline download success,
checksums, corrupt files, collisions, cancellation, provider filtering, folder
persistence, worker lifetime, and the end-to-end UI; inspect both themes and run
regressions/startup smoke test. Preserve all prior fixes and dist artifacts.

### Download-and-add verification

Implemented core/downloads.py and ui/download_dialog.py; connected the new chooser
in main_window.py and reused the ordinary AddApplicationDialog for final review.
The installer and new downloads share download_verified for format/size/checksum
validation. New-file publication uses Linux no-replace rename (atomic link fallback
on older systems), rejecting collisions and checking file identity before review
and registration. Candidate filtering also excludes obvious images/docs/checksum
lists. No schema change or new dependency. Destination preferences reuse discovery.

New coverage: 46 offline tests in tests/test_downloads.py, including actual AppImage
validation, initial downloads, collisions/races, cancellation, source filtering,
discovery folder persistence, modal worker closure and the complete main-window
link → download → review → register flow. The full regression run before the final
two safety cases passed **644 tests, 12 skipped, 1 existing Qt deprecation warning**.
After those final checks, the focused regression across downloads, updates, GUI,
categories and launch options passed **242 tests, 11 skipped**. All skips concern
restricted local sockets. Live provider/asset requests remain unverified here.

Final startup smoke test passed. New source chooser and download dialog were rendered
and inspected in light/dark themes. The compact 580×440 download dialog keeps its
footer visible. git diff --check passed. README, docs/DOWNLOADING.md and existing
0.6.1 notes describe the flow and limitations. The user explicitly kept version
0.6.1; SOURCE is ready for rebuilding and manual desktop testing. Existing dist
AppImages and prior work remain intact. No commit or publication was attempted;
Git metadata is still read-only in this environment.

## Confirmed 0.6.1 release preparation

User requested preparation of 0.6.1. Verified previous source version 0.6.0 at
HEAD b583139, and reviewed the current diffs/new source/tests against that base.
Active pyproject/__init__/README versions already agree on 0.6.1; no second bump.
Repository identity: /home/thilen/appforge, main, origin/main, configured origin
https://github.com/Thilen03/AppForge.git. Git metadata remains read-only here.

Finalized releases/RELEASE_NOTES_v0.6.1.md with verified download-and-add, discovery
folder reuse, update/version/checksum/architecture fixes, nightly opt-in controls,
README/usage-guide improvements, known limits and installation/upgrade instructions.
No release date was inferred. Historical notes and historical validation records
remain unchanged. Removed stale version labels from active category/discovery
headings and documented discovery/download folder sharing. No schema migration or
runtime dependency change; optional local roadmap.md was unavailable.

Full current regression: **646 passed, 12 skipped, 1 existing Qt deprecation
warning**. Skips explicitly concern restricted local TCP/Unix sockets. Used the
already installed build dependencies and local runtime for test fixtures. Final
offscreen startup smoke test passed. Validated 21 local documentation links/anchors,
Bash example syntax and git diff --check. Live provider access remains restricted;
automated tests do not establish final AppImage desktop/manual testing.

SOURCE is ready for the user to build and manually test as
AppForge-0.6.1-x86_64.AppImage. An existing file of that name is present in dist;
verified its contents, size and modification time remain unchanged during this
preparation. Its relationship to the final source and manual testing are not
confirmed. No distributable was built, renamed or modified. No staging, commit,
push, tag, upload or publication was attempted. Publication remains pending a
matching final binary and the user's explicit build/manual-test confirmation.
