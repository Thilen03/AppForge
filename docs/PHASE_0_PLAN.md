# Phase 0 inspection and implementation plan

## Confirmed 0.6.4 release preparation

User explicitly requested prepare release 0.6.4. Previous release is HEAD
93e7450 (0.6.3). Reviewed source/doc/test diffs, current README, public notes,
prior release notes and tags (local tags still end at v0.5.4); roadmap.md is
unavailable. pyproject.toml, __init__.py and README already consistently declare
confirmed 0.6.4, so preserve that version. No further source/version changes are
needed. Repository identity is /home/thilen/appforge, main, origin/main and
https://github.com/Thilen03/AppForge.git. Git metadata remains read-only; staged
diff is empty and no staging, commits, fetches, pushes, tags or uploads were made.
Finalize only releases/RELEASE_NOTES_v0.6.4.md with verified discovery filename
filtering, automatic checked existing-download continuation across sessions,
search/counts, case-insensitive header sorting and safe visible-match actions.
Keep prior notes, no inferred release date, no database/dependency changes.
Current README/DISCOVERY/DOWNLOADING already describe the implemented behavior;
wrap the DISCOVERY paragraph and add normal-user installation/upgrade guidance
to the 0.6.4 notes. Fresh full regression with the existing local fixture runtime
and .venv-build dependencies: 864 passed, 12 restricted TCP/Unix socket skips,
one existing Qt deprecation warning. Startup selftest and git diff --check passed.
Version declarations, README badge/link and notes heading agree on 0.6.4;
15 local documentation links resolve. Earlier feature validation includes modal
cancel/retry/existing-file flows, real sort-header clicks and discovery layouts
in both themes.
Initial dist/ inventory was empty, recorded in
/tmp/tuxshelf-064-preparation-assets-before.json. An AppImage appeared while
checks were running; this preparation did not build or modify it. The new file
is dist/TuxShelf-0.6.4-x86_64.AppImage, 84,736,504 bytes, observed SHA-256
6782ca3f8f3b1dc1285976a0ce64abe510d39aa00cf43e809d3dc3bce803d8bd.
Its appearance prevents claiming an unchanged inventory across preparation;
source provenance and manual testing are not inferred from its name or hash.
Observed file metadata is in /tmp/tuxshelf-064-preparation-observed-asset.json.
SOURCE 0.6.4 is prepared. Publication still requires the user's explicit
confirmation of building from the prepared source and personally testing that
exact binary. Nothing was committed or published.

## 0.6.4 discovery search and sorting plan

Add a clearable results search above DiscoveryDialog's existing table; match
case-insensitively across displayed fields including filename/location and edited
update source. Enable clickable case-insensitive text sorting, initially by app
name ascending. Bind each row to Candidate.path rather than candidate list order
so sorting cannot change selection/import/ignore/source identity. Keep checked
rows and source edits through filtering and rerenders. Select/clear/import/ignore
operate on visible eligible matches; show a matching/total count and contextual
import-all wording. Preserve existing watch-only root checkboxes and all-root
manual scans. No scanner, database or dependency changes. Update focused UI tests,
README, DISCOVERY guide and the same 0.6.4 notes. Validate sort/filter interactions,
bulk actions and source edits, rescanning/watched previews, regression suite,
selftest and populated/empty/no-match layouts in both themes. No build/publication.

Implemented clearable live results search, matching/total counts, default
case-insensitive A–Z sorting and clickable text sorting on all result columns.
Rows carry candidate paths; actions resolve those identities after sorting.
Backing source items follow their editors, including edits to the active sort
column. Filtering hides rows without discarding checks or edits; bulk select,
clear, import and ignore apply only to visible eligible results. Import-all reads
"Import all matching" during search. Search/order persist through rescans and
rerenders; roots remain all-scanned/watch-only. README, DISCOVERY and the existing
0.6.4 notes document these changes.
131 focused discovery/watch/source tests passed. New tests cover actual heading
clicks in both directions, all-field/filename search, clearing/no matches,
source editing while sorted, correct app/source import, hidden checked rows,
filtered select/clear/import-all/ignore/reset, and rescan behavior. Updated one
existing source-import test to capture paths from displayed rows rather than
assuming filesystem candidate order after default sorting.
Inspected populated, filtered and no-match layouts in both themes. Startup
selftest and git diff --check passed. Full regression with existing local runtime
and .venv-build dependencies: 864 passed, 12 restricted TCP/Unix socket skips,
one existing Qt deprecation warning. SOURCE is ready for user build/manual testing.
Source stays at confirmed 0.6.4; no build, dist changes, Git mutation or publication.

## 0.6.4 existing-download continuation correction

User clarified that same-name files must work automatically across sessions,
without manual local-file selection. Replace the previous session-only cache with
on-disk validation: open the existing regular file without following symlinks,
check selected asset size/format/published checksum, and retain an identity
signature for final Add validation. Preserve contents and permissions. Missing
checksums remain explicitly unavailable; never claim checksum verification from
a filename. Reuse existing format/checksum readers and the ordinary Add form.
Handle a same-name file appearing during download the same way without overwrite.
Remove obsolete cache wiring, update collision/retry/modal tests and rewrite current
docs/0.6.4 notes to reflect automatic reuse. Validate focused and full regressions,
startup selftest and both themes. No version bump, build or publication.

Implemented existing-file validation in core/downloads.py before download space
checks or temporary-file creation, and after concurrent no-replace collisions.
An anchored directory handle and O_NOFOLLOW/nonblocking file descriptor reject
symlinks, directories and FIFOs. Check published size, shared format validation
and shared published-checksum lookup, then hash locally with progress/cancellation.
Retain the original file identity and check for changes before returning a
DownloadResult to the normal Add form. Preserve file contents and permissions.
No session cache or MainWindow state is needed. Without a published checksum,
report it as unavailable and continue after size/format checks, as downloads do.
Updated dialog hints/progress, README, DOWNLOADING and existing 0.6.4 notes.
60 focused download tests passed, including actual modal Add flows for new,
cancel/retry and pre-existing files without session history; real AppImage reuse;
SHA-256/SHA-512/sidecar/missing checksums; modified, invalid, symlink, directory and
FIFO paths; cancellation; and valid/invalid concurrent collisions. Startup selftest
and git diff --check passed. Inspected the dialog in both light and dark themes.
Full regression with the existing local test runtime and .venv-build dependencies:
857 passed, 12 restricted TCP/Unix socket skips, one existing Qt deprecation warning.
SOURCE 0.6.4 is ready to build and manually test. No dist changes, release AppImage
build/manual testing, Git mutations or publication. Git metadata remains read-only.

## 0.6.4 discovery bug-fix plan

User confirmed 0.6.4 for discovery fixes, then clarified that manual scans must
continue scanning every saved folder and checkboxes must remain watch-only.
Restore that behavior and leave DiscoveryDialog unchanged. Reuse the shared
read-only scanner and existing format readers. Add an early filename/permission
filter before metadata inspection and watched observations, accepting common Linux
executable suffixes, extensionless and version-suffixed executables; still validate
AppImage/ELF/shebang contents. Unknown suffixes (including ROMs) are excluded even
if marked executable; users can add unusually named supported executables with
the local-file picker. Update core/discovery.py, discovery tests, public
README/discovery docs, version declarations and only the new 0.6.4 notes.
Validate all saved roots regardless of checkbox state, ROM exclusion before format
reads, supported names/permissions, watch compatibility, regression suite and
startup selftest. No schema changes, builds or publication. roadmap.md is absent.

Implemented the shared discovery filter and kept DiscoveryDialog identical to
HEAD. Regression coverage proves manual scanning includes checked and unchecked
roots; executable-marked .extm and version-named ROMs are excluded before format
reads; valid common executable names still work; data with executable suffixes
is rejected; watching does not retain unrelated observations/metadata.
Updated source version from 0.6.3 to the confirmed 0.6.4, README, DISCOVERY guide
and releases/RELEASE_NOTES_v0.6.4.md. No release date was inferred.
Validation: 44 focused discovery/watch tests passed. Initial system-Python runs
hit blocked fixture runtime downloads and missing PySquashfsImage. Reusing
.venv-build/lib/python3.14/site-packages on PYTHONPATH and
APPIMAGE_RUNTIME_FILE=/tmp/tuxshelf-test-runtime resolved those environment
issues: full suite 843 passed, 12 restricted TCP/Unix socket skips, one existing
Qt deprecation warning. Startup selftest and git diff --check passed.
SOURCE 0.6.4 is ready for the user to build and manually test as
TuxShelf-0.6.4-x86_64.AppImage. Existing dist files were not modified. No release
binary was built or manually tested; publication remains pending. Git metadata
is read-only; no staging, commit, push, tag or upload was attempted.

## Confirmed 0.6.3 release preparation

User requested prepare release 0.6.3. Verified previous release at HEAD 315bf4b
(0.6.2); active pyproject.toml, __init__.py and README already consistently name
the confirmed 0.6.3, so no further bump. Reviewed changes since HEAD, new bulk/
profile modules and tests, public docs, release history and local tags through
v0.5.4. Optional roadmap.md is unavailable. Repository identity is the main
TuxShelf directory, main, origin/main and the expected GitHub URL. Git metadata
remains read-only; the index is empty and no staging/commit/fetch/push/tag/upload
was attempted.

Finalized only releases/RELEASE_NOTES_v0.6.3.md for this version, covering bulk
categories/update preferences/menu shortcuts/library removal, click-card selection,
progress/cancellation/busy/failure handling, and independent named launch profiles
with Default compatibility and validated library transfers. Documented session-only
profile choice and older-version export compatibility. README quick start and
documentation table now point to profiles; existing USAGE/LAUNCH_OPTIONS/
LIBRARY_TRANSFER docs cover the verified behavior. No release date was inferred;
historical notes were preserved. No database migration or dependency changes.

Fresh full release regression: 823 passed, 12 restricted local TCP/Unix socket
skips, one existing Qt deprecation warning. Startup selftest and git diff --check
passed; version declarations/notes heading/expected artifact agree and 18 local
documentation links resolve. Earlier feature QA includes actual modal/editor/
worker flows, real process launches and light/dark card/dropdown/editor inspection.

Recorded the existing dist/TuxShelf-0.6.3-x86_64.AppImage (84,732,408 bytes) before
preparation and verified SHA-256, size, modification time, inode and mode unchanged
after checks. Its filename does not verify its source contents or user testing.
SOURCE 0.6.3 is ready for the user to build and manually test as
TuxShelf-0.6.3-x86_64.AppImage. Matching binary build/manual testing is unconfirmed;
publication remains pending that explicit confirmation. No distributable was built,
renamed or changed during release preparation.

## 0.6.3 launch profiles plan

Add a split Launch button with a subtle dropdown, per-card profile selection and
Edit profiles. Existing root launch/environment metadata remains the Default
profile (never duplicated or removed). Named profiles are independent snapshots
in existing metadata with validated stable IDs/names, environment variables and
launch options. New profiles copy Default; the editor supports create/rename/
delete and saves atomically with Cancel discarding drafts. Profile choice lasts
for this window session; tray/desktop launches keep Default. Deleted/missing
profiles never silently launch different settings.

Reuse the launcher, environment/options validation and existing desktop sync.
Add core/launch_profiles.py and ui/launch_profiles_dialog.py; extend LibraryService,
AppCard/MainWindow, library transfer, tests and launch docs/current 0.6.3 notes.
Keep selection-mode button exclusions and missing-file actions. Extend export/
import validation and environment opt-out to nested profiles. No database migration
or dependencies. Validate real process argv/environment/cwd, terminal handling,
Default compatibility, persistence/transfer, editor Save/Cancel/validation,
dropdown selection/card refresh, button geometry/selection safety and light/dark
UI. Run focused/full regressions and startup selftest. Preserve all current
uncommitted bulk/version work and existing dist files; no publishing.

Implemented core launch-profile validation/resolution, an independent draft editor
and a split Launch button. Default is the existing root configuration; custom
profiles have stable IDs and store complete environment/options snapshots.
New/rename/delete, atomic Save and Cancel are supported. Card dropdown selection
survives refreshes in this window; tray/details/desktop launch Default. Deleted
profiles reset visible cards to Default; stale launch requests fail explicitly.
Profile launches use the existing shell-free detached launcher and terminal route.
Library transfers validate profiles and honor environment opt-outs at both stages.
No database migration, dependency or executable/source changes are involved.
README, launch/usage/transfer docs and current 0.6.3 notes describe the feature.

Validation: new tests cover malformed/duplicate/reserved names and IDs, atomic
validation, Default compatibility, persistence, real process argv/environment/cwd,
missing profiles/folders, terminal routing, all export/import environment choices,
editor Save/Cancel/delete/rename, real dropdown/edit flow, card refresh and
selection-mode arrow independence. Full regression: 819 passed, 12 restricted
TCP/Unix socket skips, one existing Qt deprecation warning. After final split-button
height refinement and four light/dark Update/Retry geometry checks, 180 focused
profile/bulk/launch/transfer/desktop tests passed. Startup selftest and git diff
--check passed. Inspected cards, dropdown and editor in light/dark themes, including
the final aligned split button beside Retry and existing card actions. Source
remains 0.6.3; existing dist files were untouched and no AppImage build/manual
testing, staging or publication was attempted. Git metadata remains read-only.

## 0.6.3 card selection refinement

User requests the entire non-button card area as a selection target. Reuse
AppCard's checkbox signal and MainWindow selection state; handle left press/release
on the card, including events propagated from labels and nested content, excluding
button descendants (including disabled buttons). Keep checkbox/button actions and
normal-mode launching. Consume the second click of a double-click in selection
mode to avoid undoing the first selection. Update bulk UI tests, usage and the
confirmed 0.6.3 notes; no additional version bump or dist/Git metadata changes.

Implemented left-click selection across the background, title, icon, badges,
path and nested progress content. Button hit testing also excludes disabled
buttons; checkbox clicks still toggle exactly once. A release outside the card
does not select, and ordinary launching outside selection mode is preserved.
Validation: 24 bulk tests and 27 relevant UI regression tests passed, including
card content clicks, button/favorite/checkbox independence, right-clicks and
double-click behavior. Startup selftest and git diff --check passed. This changes
interaction only; the existing selection appearance and layout are retained.
No AppImage was built or changed; the refinement remains part of 0.6.3.

## Bulk library actions plan

Add explicit selection mode and card checkboxes in ui/main_window.py and
ui/app_card.py, with selection retained across card refreshes and sorting but
limited to currently matching apps. Select visible/Clear and a compact action
menu expose shared categories, update preferences, menu shortcuts and removal.
Use a dedicated dialog for update preferences with unchanged defaults. Reuse
LibraryService, UpdateService and desktop categories in a Qt-free bulk helper;
invalidate cached targets when channel/asset preferences change. No schema or
dependency changes. Keep sources and unrelated per-app metadata intact.

Process one entry per Qt event-loop turn with progress/cancellation, snapshot IDs
before modal prompts, recheck busy/missing entries and report per-app failures.
Confirm removal with names and preserve binaries/backups. Test selection/filter/
refresh, mixed preferences, persistence, shortcut failures, safe removal,
cancellation and busy races. Run relevant/full regression and startup selftest,
inspect light/dark UI, and update README/USAGE. Versions and new release notes
await release-version confirmation; preserve dist and read-only Git metadata.

Implemented the selection toolbar, accessible card checkboxes, shared-category
dialog and mixed-preference update dialog. BulkActions reuses existing library/
update/desktop services; update targets are invalidated when channel or pattern
changes. The event-loop runner snapshots IDs, checks busy status immediately
before each entry, reports individual failures, and supports cancellation between
entries without undoing completed work. Removal confirms names and preserves
application files/backups. Emptying the library exits selection mode. No schema
migration or new dependency; README and USAGE describe the workflow.

Validation: 104 focused existing/new tests passed. Full regression with existing
build dependencies and the local AppImage fixture runtime: 773 passed, 12 skips
for restricted TCP/Unix sockets, one existing Qt deprecation warning. After final
action-menu dispatch and empty-library refinements, all 14 bulk tests passed;
startup selftest and git diff --check passed. Inspected selected/unselected cards
and update settings in both light/dark themes, including the final action button.
Active version remains 0.6.2 pending a confirmed next release version. Existing
dist files were untouched; no build/manual AppImage test, staging or publication
was attempted. Git metadata remains read-only in this environment.

User subsequently confirmed that bulk actions belong in release 0.6.3. Updated
pyproject.toml, src/tuxshelf/__init__.py and README from 0.6.2 to 0.6.3, and created
only releases/RELEASE_NOTES_v0.6.3.md for the verified bulk features. Historical
notes remain unchanged; no publication date was inferred. Expected user build:
TuxShelf-0.6.3-x86_64.AppImage. Existing dist files remain untouched; matching
binary build/manual testing and publication are still pending.

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
`TuxShelf-0.6.1-x86_64.AppImage`; publication approval remains outstanding.

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
TuxShelf-0.6.1-x86_64.AppImage. An existing file of that name is present in dist;
verified its contents, size and modification time remain unchanged during this
preparation. Its relationship to the final source and manual testing are not
confirmed. No distributable was built, renamed or modified. No staging, commit,
push, tag, upload or publication was attempted. Publication remains pending a
matching final binary and the user's explicit build/manual-test confirmation.

## Application badge color preferences

Scope: independently customize each format/status badge shown on library cards.
Reuse AppSettings' existing SQLite settings table, SettingsDialog's scrollable
layout, QColorDialog and the shared theme stylesheet. Stable badge keys distinguish
statuses that share default colors. Preserve every original light/dark default;
store only explicit overrides, validate hex colors and fall back safely for corrupt
preferences. No schema migration or application-record changes are required.

Files: core/settings.py (registry and persistence), ui/settings_dialog.py (pickers,
previews and reset controls), ui/app_card.py (badge keys), ui/theme.py (defaults and
custom colors), ui/main_window.py and app.py (live/startup/theme application).
Custom backgrounds use contrasting black/white text. Save applies changes to
existing cards; Cancel discards the draft. Individual/all resets restore adaptive
theme defaults. Validate persistence, every badge mapping, cancel/save/reset,
independent colors, light/dark defaults and live theme switching; run regressions,
startup selftest and offscreen visual inspection. README and USAGE document usage.
Version/release preparation is separate and awaits a confirmed release version.

Implemented all 13 current badge choices with independent previews/pickers,
per-badge/all resets, persisted overrides, readable custom text and live application
without replacing existing cards. Added tests/test_badge_colors.py covering
validation/reopening, picker cancellation, Save/Cancel/reset, every status/format
mapping, original light/dark colors, live changes and startup restoration.

Validation: focused settings/theme tests: 74 passed, 1 socket skip. Full regression
with the existing .venv-build dependencies on PYTHONPATH and local
APPIMAGE_RUNTIME_FILE=/tmp/tuxshelf-test-runtime: 664 passed, 12 local TCP/Unix
socket skips, 1 existing Qt deprecation warning. Earlier attempts using only system
Python could not create online fixtures or import PySquashfsImage; loading the
existing dependencies/runtime resolved those setup failures. Offscreen startup
selftest and git diff --check passed. Visually inspected default/custom settings
and customized cards in light and dark themes using offscreen captures.
No distributable AppImage was built or modified, and no manual desktop/AppImage
testing is claimed. Git metadata remains read-only; no staging or publication was
attempted. Active version remains 0.6.1 pending confirmation of a release version;
no new versioned release notes were created.

## Confirmed 0.6.2 badge color refinement

User confirmed 0.6.2 and requested the original outlined/tinted badge appearance
for custom colors, with controls collapsed at the bottom of Settings. Update
ui/theme.py to use the selected text/border color and a translucent wash (slightly
stronger in dark mode); seed the picker with the text color. Move controls after
Library transfer into a keyboard-accessible expandable section, collapsed whenever
Settings opens. Preserve stored overrides, Save/Cancel/reset and original defaults.
Update badge tests for tint/text and expansion behavior, inspect both themes and
run focused/full regressions and startup selftest. Update active project versions,
README/usage and only releases/RELEASE_NOTES_v0.6.2.md; preserve historical notes.
No schema or build changes are needed. Existing AppImages remain untouched.

Implemented the 0.6.2 refinements and updated pyproject.toml, __init__.py, README,
USAGE and releases/RELEASE_NOTES_v0.6.2.md. Original defaults and existing saved
color choices are preserved. Added a keyboard expansion/collapse, bottom placement
and reopening-default test; updated color expectations to verify translucent
backgrounds and matching text across theme switches.

Validation: 23 focused badge/theme tests passed. Full regression with the existing
build dependencies and local test runtime: 665 passed, 12 restricted TCP/Unix socket
skips, 1 existing Qt deprecation warning. Startup selftest and git diff --check
passed. Visually inspected the collapsed settings, expanded controls and custom
cards in light/dark themes. Source 0.6.2 is ready to build and manually test as
TuxShelf-0.6.2-x86_64.AppImage; existing dist files were not changed. No manual
binary testing or publishing is claimed. Git metadata remains read-only here.

## Watched discovery folders plan

Add opt-in watch checkboxes to the existing Discovery folder list, persisted in the
settings table and restricted to those discovery roots. Reuse the recursive safe
scanner, metadata readers, worker signals and import preview/confirmation. Background
polling every 10 seconds avoids recursive native watcher limits and catches nested
files and reappearing directories. Require identical file observations across checks,
skip hidden/temporary downloads, and cache unchanged metadata to avoid reparsing.
Run one cancellable worker at a time with plain snapshots; SQLite stays on the UI
thread. A persistent count/review button offers the existing preview with all new
rows unchecked. Registered/ignored files must be excluded, stale results rejected
when preferences change, and quit must cancel watching while tray mode continues.

Likely files: core/discovery.py (optional filter/cache), new core/discovery_watch.py
and ui/discovery_watch.py (snapshot scan/controller), ui/discovery_dialog.py (watch
checkboxes and preview input), ui/main_window.py (banner/lifecycle), tests and
README/discovery/usage docs. No schema migration or new dependencies. Test stability,
partial/renamed downloads, recursion, duplicates, ignore/import/removal, configuration
changes, cancellation and UI review. Run focused/full tests, selftest and light/dark
visual checks. Preserve all existing uncommitted badge/version work and dist files.

Implemented watching as opt-in checkboxes on the existing Discovery roots. The
background controller polls every 10 seconds, permits one job at a time, defers
changed/new files until a matching later observation, excludes hidden/temporary
filenames and caches both app metadata and non-app detection. Normal scanner
safety, hard-link deduplication, ignored/registered checks and import validation
are reused. The main window shows a persistent count/review button, and the
existing dialog opens its pending candidates unchecked. Imports still require
selection and confirmation. Preference changes cancel/discard stale work, folder
removal disables watching, and actual quit cancels the worker while tray hiding
continues polling. No database access occurs inside the worker.

Added tests/test_discovery_watch.py for stable/cache behavior, changing and renamed
partial downloads, execute-permission changes, symlink/backup/hard-link exclusions,
missing/reappearing roots, persisted checkboxes, allowed-root restriction, no
implicit imports, ignore/import/removal counts, worker responsiveness/cancellation,
review selection and real timer-driven arrivals. Updated README, DISCOVERY, USAGE
and current uncommitted 0.6.2 release notes, preserving previous versions and the
badge work. No schema migration or new dependency was introduced.

Validation: 108 focused discovery/download/tray/badge tests passed. Full regression
using existing build dependencies and the local AppImage fixture runtime:
676 passed, 12 restricted local TCP/Unix socket skips, 1 existing Qt deprecation
warning. Offscreen startup selftest and git diff --check passed. Inspected folder
checkboxes, unchecked preview and the new-app count in light/dark themes. Active
version remains the confirmed 0.6.2 for this ongoing uncommitted update. Source is
ready for building and manual desktop/AppImage testing; existing dist files remain
untouched. No staging, commit or publishing was attempted; Git metadata is read-only.

## Embedded AppImage update-source suggestions plan

Inspect embedded update information without executing AppImages or making network
requests. Follow AppImageSpec: Type 2 ELF .upd_info and Type 1 ISO volume descriptor
field at offset 33651. Reference:
https://github.com/AppImage/AppImageSpec/blob/master/draft.md#update-information
Read bounded ELF section headers/string table/update text (32/64-bit, either byte
order), gracefully ignore absent/malformed/unsupported information and preserve
metadata fallback. Map gh-releases-zsync and recognizable HTTPS repository release
URLs from zsync to source suggestions, using existing provider normalization; do
not guess repositories from generic servers or implement a new updater transport.

Add a Qt-free format helper and attach only validated suggestions to AppMetadata.
Local Add prefills a reviewable/editable field without replacing manual/download
sources, and clears obsolete auto-suggestions on file changes. Discovery previews
(including watched arrivals) show per-row editable update sources; import explicitly
confirms/passes the selected sources through the existing service. Keep source
choice separate from raw inspection metadata and preserve all existing update,
checksum, backup and import validations. No automatic channel/pattern changes.

Files: new formats/appimage_update.py, formats/appimage.py, ui/dialogs.py,
ui/discovery_dialog.py, core/discovery.py, tests and user docs/current 0.6.2 notes.
No database migration/new dependency. Verify malformed/bounded ELF parsing,
transport/URL validation, no execution/network, Add edit/clear/async precedence,
manual/discovery/watched imports and real AppImage integration; run focused/full
regressions, startup selftest and light/dark UI inspection. Preserve ongoing 0.6.2
badge/watching changes and all existing dist files.

Implemented a bounded offline update-info reader for Type 2 .upd_info ELF sections
and the Type 1 volume field, including ELF32/ELF64, both byte orders and extended
section numbering. Only validated supported repository suggestions enter metadata;
unsupported/malformed strings, oversized ranges and arbitrary embedded URL/string
matches are ignored. Recognition covers gh-releases-zsync and recognizable HTTPS
GitHub/Forgejo/GitLab-style zsync release URLs, including custom server ports.
No zsync transport, source verification request, asset glob or channel setting is
silently installed. Optional extraction remains available even if name/icon reads
fall back because the embedded filesystem cannot be read.

Local Add marks the prefilled source as a suggestion and preserves manual edits,
explicit clears and repository download choices. File changes remove outdated
auto-suggestions, and inspection tokens now advance even for duplicate selections
so an older result cannot fill a newer selection's source. Discovery/watched previews
show per-row editable sources and validate chosen sources before confirmation;
import_candidate receives the explicitly chosen source rather than applying hints
implicitly. Existing registered apps are not relinked.

Added tests/test_appimage_sources.py with parser/transport/malformed-input tests,
manual edit/clear/download/async precedence, per-row import sources, non-section
decoys and a real packaged AppImage inspection that forbids execution and network
calls. Added an optional update_info fixture-builder argument solely for test
AppImages. Updated README, USAGE, DISCOVERY and the current 0.6.2 release notes.
No database migration/new dependency; confirmed version remains 0.6.2. Inspected
Add and discovery suggestions in light/dark themes. Final focused validation:
151 passed; offscreen startup selftest and git diff --check passed. The new GUI
module uses the existing explicit Qt widget teardown fixture; its first standalone
run exposed interpreter-exit cleanup ordering, resolved before regression runs.

Final full regression on the completed source with existing build dependencies and
local AppImage fixture runtime: 736 passed, 12 restricted local TCP/Unix socket
skips, 1 existing Qt deprecation warning. Source 0.6.2 is ready for the user to build
and manually test TuxShelf-0.6.2-x86_64.AppImage. Existing dist files were not changed;
fixture AppImages were generated only in temporary test folders. No manual testing
of a new distributable, staging, commits or publication is claimed. Git metadata
remains read-only in this environment.

## Source-detection feedback and metadata fallback

User reports WiiCompiled-Setup-x86_64.appimage from patchzyy/Wiicompiled yielded
no suggestion or detection message. The file is not present in this workspace;
public repository/releases pages are readable, but direct download/API DNS and
upstream packaging-file retrieval are unavailable here. Do not infer that its
embedded update field is absent, or claim a WiiCompiled-specific fix without the
actual file. The previous implementation checks only supported update-info fields
and silently leaves the generic field hint when no suggestion is available.

Add an explicit negative detection result in Add/discovery, retaining manual source
choices. Extend the existing AppStream reader to consider explicit vcs-browser URLs
(and recognized repository-root homepage URLs on known providers), preserving
update-info priority and ignoring ambiguous/unrelated metadata. Support namespaced
AppStream XML; do not search filenames or arbitrary binary strings, or add a
WiiCompiled-specific mapping. Reference AppStream URL roles:
https://www.freedesktop.org/software/appstream/docs/chap-Metadata.html
Use provenance labels to distinguish update-info from AppStream suggestions. Add
focused fallback/precedence/negative-feedback tests, then regressions, startup and
light/dark checks. Document the narrower guarantee and exact-file verification
limit; retain the current confirmed 0.6.2 work and dist artifacts.

Implemented explicit no-source feedback in Add and discovery, plus provenance-aware
messages for dedicated update info and AppStream suggestions. AppStream XML now
supports namespaces and prefers unambiguous vcs-browser repository roots over
known-provider repository homepages. Dedicated update information keeps priority;
matching desktop name/component ID avoids using a bundled dependency's repository.
Manual sources/clears and download-source precedence remain intact. No arbitrary
filename/string/website guessing or WiiCompiled-specific source mapping was added.

Validation: 125 focused source/discovery/core tests passed. Full regression with
existing build dependencies/local fixture runtime: 756 passed, 12 restricted local
TCP/Unix socket skips, 1 existing Qt deprecation warning. Startup selftest and git
diff --check passed. Visually inspected explicit no-source feedback and AppStream
fallback in light/dark themes. A real temporary AppImage with AppStream-only source
metadata is covered by tests. A synthetic fixture with the reported WiiCompiled
filename tests missing-metadata feedback only; it is not the user's actual file.
Exact WiiCompiled metadata and the cause for that binary remain unverified pending
an attached copy. This environment could not retrieve the binary; do not claim its
field is absent or that this exact case is fixed. Current version stays 0.6.2;
existing dist files are unchanged and no publishing/staging was attempted.

## Visible automatic-source detection in the actual local Add flow

User reports no observable attempt or result across multiple local AppImages.
Refocus on the workflow rather than a particular binary. Current detection is
called by _InspectJob, but status is mixed into a small scrolling field hint and
there is no dedicated checking state. Add a persistent, explicitly titled source
status panel above Add/Cancel, outside the scrolling form. Report waiting, checking
(with indeterminate progress), found (including the URL), not found, failed and
not-applicable states independently of source field validation/manual editing.
Keep async token protection, metadata readers and manual/download precedence.

Verify the actual MainWindow Add Application -> source chooser -> local Add form
-> Browse -> real inspection worker -> result -> Add flow, driving real modal
widgets and stubbing only the OS file chooser/network checks. Hold the worker to
verify visible progress, then test found/not-found/error, file changes, small-screen
visibility and manual source preservation. Update usage/notes, run focused/full
regressions, selftest and light/dark UI QA. Do not build or modify dist binaries;
existing single-instance/tray behavior means a running old copy must be exited
before testing updated source or a newly rebuilt AppImage. Preserve all current
0.6.2 source work; no metadata/source-reader expansion is part of this correction.

Implemented the persistent Automatic update-source detection panel in
ui/dialogs.py, with matching light/dark styling in ui/theme.py. It lives outside
the scroll area above Add/Cancel and reports waiting/checking/found/not-found/failed,
plus explicit duplicate/non-AppImage outcomes. A real indeterminate bar is visible
during inspection. The found state includes the detected URL even when a manual
source is retained. Field validation and scrolling no longer replace/hide the
visible outcome. Long messages are shortened visually with full accessible text
and a tooltip. No artificial delay or new source guessing was introduced.

New tests/test_source_detection_flow.py drives MainWindow's actual Add button,
real source chooser/local dialog, Browse button, real _InspectJob and Add action.
Only the OS file chooser and post-add network check are stubbed. It verifies
checking across event-loop turns, source persistence, negative/error results,
small-window visibility, independent validation, scrolling, manual precedence and
stale-result rejection. Existing source-reader/discovery/download tests still run.

Validation: 131 focused tests passed. Full final regression with existing build
dependencies/local fixture runtime: 761 passed, 12 restricted TCP/Unix socket skips,
1 existing Qt deprecation warning. Startup selftest and git diff --check passed.
Inspected checking/found/not-found/failed at 520x440 in light and dark themes.
USAGE and current 0.6.2 notes describe the fixed visible workflow. Current source
is ready for building/manual testing; existing AppImages are unchanged and there
was no staging or publishing. A previously running tray instance or previously
built binary cannot show newer source changes until it is exited/rebuilt/relaunched;
this was not verified as the cause of the user's report.

## Confirmed 0.6.2 release preparation

User requested prepare release 0.6.2. Verified previous release source at HEAD
3d92ef9 (0.6.1); active pyproject.toml, __init__.py and README already consistently
identify the confirmed 0.6.2, so no additional version bump. Reviewed current diffs,
new modules/tests, existing notes and available local tags (through v0.5.4).
Optional roadmap.md remains unavailable. Repository identity is the main TuxShelf
directory, branch main, upstream origin/main, origin
https://github.com/Thilen03/AppForge.git. Git metadata remains read-only; the index
has no staged changes and no staging/commit/push/fetch/tag/upload was attempted.

Finalized only releases/RELEASE_NOTES_v0.6.2.md for this version: customizable badge
colors and original defaults, collapsed controls, opt-in watched discovery folders,
explicit preview/import, source metadata/AppStream suggestions and the persistent
local Add detection panel. Documented the previous-file selection fix, metadata
limits and periodic/stable-file watching limitations. README, USAGE and DISCOVERY
already describe the verified features and match source. No publication date was
added; historical release notes were preserved. No dependency/schema migration.

Fresh release regression: 761 passed, 12 restricted TCP/Unix socket skips, 1 existing
Qt deprecation warning. Startup selftest passed. Validated matching active versions,
notes heading/expected artifact name and 21 local file links. git diff --check passed.
Earlier feature verification includes real local Add modal/worker tests and
light/dark inspection at small sizes; automated checks are not manual binary tests.

Recorded the existing dist/TuxShelf-0.6.2-x86_64.AppImage (84,707,832 bytes) before
preparation and confirmed its SHA-256, size, modification time, inode and mode were
unchanged afterward. Its name alone does not verify that it contains this source.
SOURCE 0.6.2 is ready for the user to rebuild and manually test as
TuxShelf-0.6.2-x86_64.AppImage. Matching binary build/manual testing is unconfirmed;
release publication remains pending that explicit confirmation. No distributable
was built, renamed or changed during preparation.

## 0.6.5 card actions and TuxShelf release notes

Use the existing primary button style for Update/Retry update. Add an offline
TuxShelf notes dialog using the existing safe Markdown document and link handler.
Bundle current public notes as package data; test equality to prevent drift.
Store suppression and last-shown version in existing settings (no migration).
Show once per version only when the real main window becomes visible; hidden
login startup defers it. Settings can undo suppression and replay current notes.
Update active version, README and usage guide; preserve historical notes and dist.
Validate preferences, startup/restart gating, settings cancellation, both themes,
focused/full tests and startup selftest. No roadmap file is available.

Implemented 0.6.5 with solid primary Update/Retry update buttons, a bundled safe
Markdown notes dialog, persistent suppression/last-shown-version preferences and
Settings replay. Existing package-data/PyInstaller resource inclusion covers the
notes; a test keeps them identical to the public 0.6.5 notes. README, usage and
publishing guidance updated. No database migration or dependency changes.
Validation: 64 focused tests passed; after the final Settings layout adjustment,
26 relevant tests passed. Full regression with existing .venv-build dependencies
on PYTHONPATH and /tmp/tuxshelf-test-runtime: 871 passed, 12 restricted TCP/Unix
socket skips, one existing Qt deprecation warning. The initial system-Python full
run was interrupted after missing PySquashfsImage caused fixture-related failures;
the complete rerun above uses the already installed project dependencies. Startup
selftest and diff whitespace check passed. Visually inspected card, offline notes
and Settings screenshots in light/dark themes. Source 0.6.5 is ready for the user
to build and manually test. No AppImages built/modified and no Git metadata writes,
commits or publishing performed; Git metadata remains read-only in this environment.

## 0.6.5 optional TuxShelf launcher

Replace bootstrap's unconditional self launcher creation with persistent opt-in.
Use desktop/selflauncher for safe create/remove operations and existing source/
AppImage startup commands. Preserve existing owned shortcuts on upgrade; never
overwrite/delete foreign entries or follow symlinks. Ask once on first visible
startup, before bundled notes, and allow later creation/removal through Settings.
Refresh only opted-in shortcuts after moving/updating. Extend existing settings
without migration, keep this ongoing update at 0.6.5, and update current notes,
README and usage. Test decisions, refresh/removal persistence, file ownership,
errors and source/AppImage commands, then run regression and startup selftest.

Implemented opt-in bootstrap and a once-only first-visible-start prompt ahead of
release notes. Settings now creates/removes the TuxShelf menu shortcut with Save;
Cancel leaves it unchanged. Existing managed entries are adopted and refreshed;
explicitly disabled shortcuts are never recreated. The strict selflauncher API
uses the existing stable AppImage/source startup command, atomic writes, ownership
markers and symlink checks, and reports errors. Foreign entries and user files
are preserved; corrupt entries do not crash preferences. Updated README, usage,
public 0.6.5 notes and their bundled copy. Version remains 0.6.5 as this is a
continuation of the same development update; no migration/dependency changes.
Validation: 56 focused tests passed, one restricted socket skip. Final full
regression (including two additional corruption/prompt-error tests): 885 passed,
12 restricted TCP/Unix socket skips and one existing Qt deprecation warning.
Startup selftest and whitespace checks passed. Inspected the prompt and Settings
in both light/dark themes at 560x660. Source is ready to build and manually test;
no release AppImages were built or touched, and no Git metadata writes, commits
or publication were performed.

## 0.6.5 Utilities and moved-AppImage consent

Use Utility as TuxShelf's sole main category in packaged and generated entries.
Compare the current APPIMAGE path with the owned launcher's saved executable before
startup refresh. Queue a first-visible-window repair prompt for changed paths;
never rewrite that shortcut before Yes. No leaves it intact and asks next launch,
not repeatedly in the same session. Keep ordinary same-path starts quiet, preserve
opt-outs/foreign entries, and avoid implicit repair on unrelated Settings saves.
Extend launcher tests for unchanged/moved/renamed/declined/repaired paths, failures
and categories; update current 0.6.5 notes and usage, then validate startup and UI.

Implemented Utilities-only categories in the packaged entry and both TuxShelf
entry renderers. Startup detects an owned shortcut's changed AppImage path before
any refresh and defers a plain-text Yes/No repair prompt until the window is visible.
The prompt shows old/new locations; Yes uses the existing guarded atomic writer,
No preserves the entry and repeats only next session. Same-path starts do not
rewrite unchanged entries/icons or show a repair prompt. Same-path legacy category
entries migrate to Utilities. Disabled shortcuts stay disabled; unrelated Settings
saves no longer rewrite an enabled existing launcher. Updated README, usage and
public/bundled 0.6.5 notes. Existing historical notes and versions preserved.
Validation: 66 focused checks passed with one socket skip before adding the legacy
category migration case. Final full suite including that case: 894 passed, 12
restricted TCP/Unix socket skips, one existing Qt deprecation warning. Startup
selftest, packaged desktop-file-validate and whitespace checks passed. Inspected
repair prompts in light/dark themes. Source remains 0.6.5 and is ready for user
build/manual testing; no distributable AppImage or Git metadata was modified, and
no commit, push or publishing was performed.

## Confirmed 0.6.5 release preparation

User explicitly requested prepare release 0.6.5. Previous release is HEAD
b403e3f (0.6.4); local tags still end at v0.5.4. Source declarations and README
already agree on confirmed 0.6.5. Repository identity verified as
/home/thilen/appforge, main, origin/main, https://github.com/Thilen03/AppForge.git.
Git metadata is read-only; staged diff is empty. Preserve all existing changes,
historical notes and dist files. No roadmap file is available. Review changes
against 0.6.4 and finalize only current public/bundled notes with verified blue
Update/Retry update buttons, offline per-version notes and opt-out/replay,
optional Utilities shortcut and moved-AppImage repair consent. Add user-facing
KDE custom-menu override limitation and installation/upgrade guidance, without a
date or speculative claims. No source behavior/version changes needed. Run notes/
launcher checks and startup/desktop validation; reuse the completed full regression
for this unchanged source (894 passed, 12 socket skips, one Qt warning). Initial
dist AppImage inventory is empty, recorded in
/tmp/tuxshelf-065-release-assets-before.json. No building, staging or publishing.

Preparation complete: active declarations/README and current public/bundled notes
agree on 0.6.5. Finalized notes include verified features, normal-user upgrade
guidance and the confirmed KDE custom-menu override limitation; no release date
was inferred. Added the same KDE guidance to USAGE. No behavior/version changes
were needed. Thirty focused notes/launcher tests passed, startup selftest and
packaged desktop-file-validate passed, git diff --check passed and 17 local docs
links resolve. Latest full regression for the unchanged application source remains
894 passed, 12 restricted TCP/Unix socket skips and one existing Qt warning.
Initial dist inventory was empty. An AppImage appeared during preparation:
dist/TuxShelf-0.6.5-x86_64.AppImage, 84,748,792 bytes, SHA-256
677d597f4140692195ea47b415f66f9332a0c3f86afb76dabe30ff4432b5ad4c.
Observed metadata is recorded in /tmp/tuxshelf-065-release-assets-observed.json.
This preparation did not build, rename or modify that asset. Concurrent appearance
prevents claiming an unchanged inventory; its source/notes agreement and manual
testing are unconfirmed. SOURCE 0.6.5 is ready for the user to build and manually
test as TuxShelf-0.6.5-x86_64.AppImage. Publication is not approved or ready until
that matching build and personal testing are explicitly confirmed. Git metadata
remains read-only; no staging, commit, fetch, push, tag or upload was performed.


## 0.6.6 TuxShelf rename

Rename the application, Python package, executable, resources, desktop identity,
packaging and public/private project Markdown to TuxShelf. Reuse the existing UI,
library database, settings, updater and desktop services. Keep the established
working directory and actual GitHub remote address; do not change Git metadata,
backups or existing built artifacts. Retain narrowly scoped compatibility for
earlier libraries, environment overrides, JSON exports and managed shortcuts,
without modifying application files or adopting foreign/symlink entries. Verify
imports, packaging paths, startup, desktop integration, data continuity and the
automated suite; inspect the renamed UI in both themes. No AppImage build or
publication is authorized by this rename.

### Rename implementation and validation

Implemented source version 0.6.6: renamed the Python package to `tuxshelf`, its
entry point, resource filenames, desktop identity, KWin callbacks, notifications,
UI text, packaging, publishing asset selection, scripts and tests. Updated all
37 project Markdown files, including historical notes and local instructions;
preserved the real working-directory and configured remote addresses. Current
public notes are `releases/RELEASE_NOTES_v0.6.6.md` and match the bundled copy.

Compatibility reuses an earlier library in place when no new library database
exists (even when the new directory is empty), retains existing settings/icons/
backup paths, accepts earlier environment overrides and library JSON formats,
retains owned shortcut filenames for existing pins, and refreshes their content
with TuxShelf branding. Foreign or symlink compatibility entries are not adopted.
Moved AppImage shortcut repair still requires user consent. Existing legacy
installations share the old lock/socket identity, and saved window geometry is
carried forward without overwriting the current preference. No schema migration
or application-file move is needed.

Validation used installed build-environment dependencies on PYTHONPATH and a
local runtime read from an existing backup solely for temporary AppImage test
fixtures. The full suite passed with 909 passed, 12 local TCP/Unix socket skips
and one Qt drag-event deprecation warning. A subsequent empty-new-directory
compatibility refinement passed the focused core/autostart/instance/compatibility
checks: 74 passed, one restricted Unix-socket skip. The renamed offscreen startup
smoke test passed; library, Settings and release notes were visually checked in
light/dark themes. Shell syntax, publishing push dry-run and diff whitespace
checks passed. A path audit confirms every tracked project file retains an
existing or renamed counterpart. Remaining old-name references are compatibility
identifiers and actual local/repository addresses.

Existing dist files were hash-checked unchanged. No application AppImage was
built, renamed or manually tested; source is ready for the user to build and test
`TuxShelf-0.6.6-x86_64.AppImage`. Git metadata remains read-only here; no staging,
commit, push, tag, upload or remote repository rename was performed.


## 0.6.6 title-bar suffix correction

The main window already requests `TuxShelf <version>`, but Qt platform plugins
can append the shorter application display name to that title. Set the Qt display
name to the same full title, while retaining the stable application id and
desktop-file identity. Update active versions and bundled/public notes. Validate
actual bootstrap metadata, the main-window title, related GUI tests and the
startup smoke test; the offscreen backend cannot verify native KDE decorations.

Implemented the title-bar correction within version 0.6.6 with the Qt application display name matching the main
window's complete `TuxShelf <version>` title. Stable application/desktop ids are
unchanged. Updated active version declarations, README and matching public and
bundled 0.6.6 notes; earlier notes retained. Related release-notes, launcher and
rename-compatibility tests: 46 passed. Actual bootstrap title/display metadata
was checked in separate light/dark offscreen runs with only the unavailable
socket guard and interactive event loop substituted. Offscreen startup smoke
test and diff whitespace check passed. Native KDE decoration requires user
verification with the rebuilt AppImage; no AppImage was built or modified.

User confirmed the title-bar fix belongs to the ongoing 0.6.6 release. Active
versions and README were restored to 0.6.6, the fix was merged into its public
and bundled notes, and the newly created, unpublished 0.6.7 notes were removed.
The title-bar fix itself remains in place. Existing binaries are untouched.


## Confirmed 0.6.6 release preparation

User explicitly requested preparation of 0.6.6, retaining the title-bar fix in
this version. Previous source release is HEAD 45a68c8 (0.6.5); local release tags
end at v0.5.4, so the 0.6.5 commit and notes are the comparison baseline. Active
pyproject, package and README references already agree on 0.6.6. Repository
identity remains /home/thilen/appforge, main, origin/main and the existing GitHub
remote. Git metadata remains read-only; no staging or publication is authorized.

Preparation: review the rename/compatibility changes and prior development
context, finish only the current version's public and bundled notes, explicitly
explain the distinctive name and changed startup command, polish grammatical
artifacts of the rename, run the full available automated suite and startup
checks, and verify every existing dist file remains unchanged. README already
contains the requested front-page rename explanation and current highlights.
No roadmap.md is present. Do not build or modify an AppImage or infer manual
build/test approval from an existing filename or automated metadata inspection.

### 0.6.6 preparation result

Confirmed source 0.6.6 against previous release 0.6.5. Final public notes and
bundled notes are identical and describe the AppForge-to-TuxShelf rename and
its rationale, updated application identity/commands, existing-data/export/
shortcut compatibility and the duplicate-title fix. The command-name change is
explicitly listed under Breaking changes. No publication date was added. README
already covers these changes and upgrade guidance. Corrected four remaining
rename-related articles in import UI/errors, launcher logs and a source comment.

Full automated suite: 910 passed, 12 restricted TCP/Unix socket skips, one Qt
drag-event deprecation warning, in 120.19 seconds. Focused transfer, compatibility
and bundled-notes checks after final wording changes: 82 passed. Offscreen
startup, shell syntax and diff whitespace checks passed. Final bundled notes were
visually reviewed in both themes. Offline `release --dry-run` passed local checks
without staging, fetching, committing, pushing or contacting GitHub. Remote
authentication and release/tag availability remain unverified.

An existing dist/TuxShelf-0.6.6-x86_64.AppImage (84,748,792 bytes, SHA-256
6986c56c2a9557797344262957e5ad3d19d8c2a16ef91ae1e4af4572018f1d18) has embedded
name TuxShelf and version 0.6.6, but its bundled notes differ from the finalized
source notes. Therefore it must be rebuilt from the finalized source and manually
tested by the user before publishing. This inspection did not execute the binary
and establishes neither source provenance nor manual testing. All existing dist
files, including the earlier backup, were hash-checked unchanged. No provenance
record or test evidence was manufactured. SOURCE is ready for the user to build
and test; release publication is not ready or approved. Git metadata remains
read-only here and no Git metadata changes or publication were attempted.


## 0.6.7 custom icon URL plan and implementation

User requested direct image links alongside local custom icon selection and
confirmed version 0.6.7 (previous active version 0.6.6). No roadmap.md is present.
Reuse Add/Edit custom-icon persistence and the existing HTTPS certificate helper.
Add core/icon_download.py for bounded, cancellable HTTP(S) downloads and
ui/icon_url_dialog.py for worker signals, progress, decoding and temporary PNG
previews. Wire both forms in ui/dialogs.py; update README, USAGE, active versions,
public/bundled notes and focused tests. Existing icon files, metadata/default
reset behavior and desktop integration use the existing service; no database or
dependency changes. Preserve unrelated user modifications. Git remains read-only.

Implemented download/retry/cancel, 10 MB transfer and converted-file bounds,
16-million-pixel decoding limit and rejection of unreadable content. No user token
is attached; network errors avoid echoing URL query secrets. Tests cover invalid
schemes/credentials, unknown-length oversized downloads, declared length, empty
responses, network errors, progress, worker retry/cancellation, Add/Edit storage,
metadata refresh and default reset in both themes. Existing dist files are not
built or modified; manual AppImage testing remains the user's next step.

Validation: full regression using the existing local fixture runtime and build
dependencies completed with 929 passed, 12 restricted TCP/Unix socket skips and
one existing Qt deprecation warning. After the final version/docs and cancellation
test edits, 40 focused icon/source/compatibility/bundled-notes checks passed.
Offscreen startup selftest and git diff --check passed. The URL dialog was visually
reviewed in light and dark themes. Live internet image retrieval was not exercised
in this network-restricted environment; transfers used controlled response data.
SOURCE 0.6.7 is ready for user build/manual testing of
TuxShelf-0.6.7-x86_64.AppImage. No build, staging, commit, push or upload was run.

## 0.6.7 renamed-folder build launcher fix

Inspected build_appimage.sh after the user reported pip's interpreter still
pointing to /home/thilen/appforge/.venv-build/bin/python3. The environment's
current Python runs and imports pip/PyInstaller, but its console scripts retain
old absolute shebangs. Plan and fix: use bin/python3 -m pip and -m PyInstaller
in the existing build script, preserving the environment, packaging flow and
all existing artifacts. Updated build guidance and the ongoing 0.6.7 public/
bundled notes. Added a simulated build test with broken old console launchers
and a path containing spaces; it checks both pip calls and reaches PyInstaller
through the correct interpreter, then stops before any bundling. Eight focused
build/notes checks, Bash syntax and diff whitespace checks passed. The current
build interpreter also successfully imported both modules. No dependency install,
real build, dist mutation or Git metadata mutation was performed. The user should
rerun ./scripts/build_appimage.sh; a complete build remains unverified here.

## Confirmed 0.6.7 release preparation

User requested preparation of 0.6.7. Compared working changes with HEAD 4b69f27
(Release 0.6.6); local tags still end at v0.5.4. The active project/package
versions and README already identified 0.6.7. No roadmap.md is present.
Preserved existing source/test changes and prior release notes. Finalized public
and bundled notes for custom image URLs, bounded/cancellable downloads, the
renamed-folder build launcher fix and the renamed GitHub repository. Corrected
outdated repository wording in README and USAGE. No publication date was added.

Repository root is /home/thilen/tuxshelf, branch main, upstream origin/main.
Local origin still points to https://github.com/Thilen03/AppForge.git, so
publication is blocked pending the user's terminal remote update to
https://github.com/Thilen03/TuxShelf.git. Git metadata is read-only here; no
staging, commit, fetch, push, tag or upload was attempted.

The initially present dist/TuxShelf-0.6.7-x86_64.AppImage was only read, never
executed or modified by preparation commands. Its initial and intermediate SHA-256 was
e91044642c5dd1c47f9b7122de0d285db8373318c94e1e77b6171ece483ad87a.
Its bundled notes differ from the finalized notes, so the user must rebuild from
the prepared source and manually test the matching binary before publication.
No provenance or manual-test approval is inferred from its presence.
At the final check dist/ was empty and the asset was no longer available;
its final hash therefore could not be verified. No command to remove it was
issued. A new matching build and manual test are required.

Validation for this preparation: 104 focused checks passed, one restricted Unix
socket skip. Full regression with existing build dependencies on PYTHONPATH and
a local fixture runtime copied from appimagetool: 931 passed, 12 restricted
TCP/Unix socket skips, one Qt drag-event deprecation warning (121.84 seconds).
Offscreen source startup selftest, build/publish shell syntax, version/note
consistency and diff whitespace checks passed. Live internet image retrieval
was not exercised; URL tests use controlled responses. SOURCE 0.6.7 is ready
for the user to build and manually test; publication remains blocked as above.
