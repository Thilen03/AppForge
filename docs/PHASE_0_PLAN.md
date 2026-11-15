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
APPIMAGE_RUNTIME_FILE=/tmp/appforge-test-runtime: 664 passed, 12 local TCP/Unix
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
AppForge-0.6.2-x86_64.AppImage; existing dist files were not changed. No manual
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
and manually test AppForge-0.6.2-x86_64.AppImage. Existing dist files were not changed;
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
Optional roadmap.md remains unavailable. Repository identity is the main AppForge
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

Recorded the existing dist/AppForge-0.6.2-x86_64.AppImage (84,707,832 bytes) before
preparation and confirmed its SHA-256, size, modification time, inode and mode were
unchanged afterward. Its name alone does not verify that it contains this source.
SOURCE 0.6.2 is ready for the user to rebuild and manually test as
AppForge-0.6.2-x86_64.AppImage. Matching binary build/manual testing is unconfirmed;
release publication remains pending that explicit confirmation. No distributable
was built, renamed or changed during preparation.
