# Phase 7: integration and regression verification

## Scope and implementation plan

Reuse the existing services and feature tests. Add one focused integration module
for populated database upgrades/reopens and the discovery → update → backup →
rollback → storage → transfer workflow. Exercise the real installer with an
in-memory HTTP response at its network boundary so checksum, cancellation,
validation and atomic replacement checks can run without socket permissions.
Retain the existing real HTTP/AppImage and process tests as independent checks.

Review the obsolete provider rejection expectation against current self-hosted
support. Investigate AppImage fixture setup rather than suppressing its failures.
Fix demonstrated resource cleanup defects with small changes to existing code.
Update README and roadmap with actual results and desktop verification limits.
No new runtime dependencies, feature UI, schema migrations or architectural changes
are planned for the initial regression pass. The subsequently confirmed 0.6.0
preparation is recorded below; the category follow-up is in `CATEGORIES.md`.

## Baseline

Clean working tree before work. Full suite: **422 passed, 3 failed, 31 setup
errors**. The provider test still rejects HTTPS self-hosted sources added in 0.5.4.
The other failures require blocked TCP/Unix sockets. Fixture creation invokes
appimagetool, which attempts to download its runtime from GitHub and fails; stderr
was previously discarded. These restrictions are not application test successes.

Compatibility risks: preserve populated JSON metadata and settings during SQLite
upgrades; retain backups, notes identity, menu IDs and update preferences across
restart/rollback. Inject only HTTP transport in offline tests; do not mock installer
validation, filesystem operations or database behavior. Existing AppImages in
`dist/` and read-only Git metadata remain untouched.

## Changes and coverage

| Area | Evidence |
| --- | --- |
| Fresh and existing databases | New tests migrate empty v0 and populated v1/v2 databases, reopen twice, and compare every application field, backup metadata, categories, repository, launcher preferences and settings. No new schema version. |
| Cross-feature lifecycle | Discover/import a script, link repository, check/select release, verify SHA-256, install with real filesystem operations, reopen, inspect details/storage, repair launcher, roll back, reopen, delete approved backup, export/import, reconnect missing file. |
| Update history and preferences | Installed version, checksum/last-install metadata, cached notes, notification marker, favorites, recent launches and background setting survive restart; rollback version/history survives another restart. No new history UI or unbounded event log. |
| Failure safeguards | Six offline transport cases: connection failure, truncation, checksum mismatch, invalid executable, cancellation and atomic-swap failure. Assert unchanged app bytes/mode, no temporary files or spurious backups, and closed file descriptors. |
| Hidden-window integration | Real check/install Qt workers update two applications via tray actions; the existing confirmation is used, the window is hidden during downloads, tray count refreshes and one completion summary is emitted. Only provider/HTTP transport and user confirmation are substituted. |
| Drag/drop | Real Qt drag/drop events route local files into the existing add flow; remote URLs are excluded and dropping does not bypass registration confirmation. |
| Existing behavior | Existing core, format, desktop, provider, asset-selection, update, self-update, filtering, notifications, discovery, details, notes, transfer, storage, favorites, tray, autostart, KWin and publishing tests retained. |

The only runtime change is closing the download temporary descriptor before a
connection failure can escape: `_download` now enters the file context before the
HTTP context. This prevents a descriptor leak after repeated failed downloads.
No feature expansion, new dependency, schema migration or UI redesign.

Test infrastructure changes:

- The legacy provider test now verifies supported HTTPS self-hosted sources and
  rejects insecure HTTP, preserving the current product behavior.
- AppImage fixture creation accepts optional `APPIMAGE_RUNTIME_FILE` and reports
  tool stderr on failure. AppImage launch tests explicitly request extraction mode
  through per-app environment settings; environment sanitizing remains unchanged.
- Real TCP/Unix tests use permission probes. Only `PermissionError` causes an
  explicit skip; assertions and other errors still fail. All original transport
  and process assertions remain enabled on hosts permitting sockets. These skips
  are verification gaps, not successful networking or handoff tests.

## Verification results

1. Original baseline with system Python: **422 passed, 3 failed, 31 setup errors**.
2. After the initial changes, the same system environment: **435 passed, 2 failed,
   31 setup errors**, plus one Qt warning. This confirmed the provider mismatch was
   resolved without disguising the fixture/socket restrictions.
3. The local-runtime probe exposed another environment issue: system Python lacks
   `PySquashfsImage`, while the existing `.venv-build` contains the declared runtime
   dependencies. Using those dependencies and an offline runtime enabled all real
   AppImage fixtures. Before capability probes: **456 passed, 2 failed, 10 setup
   errors**, all remaining failures/errors involving prohibited sockets.
4. Final full suite with the explicit environment below: **456 passed, 12 skipped,
   no failures or errors**. Eleven skips need TCP sockets and one needs Unix sockets
   and process handoff. One deprecation warning comes from Qt's older QPoint
   `QDragEnterEvent` constructor, retained for compatibility with supported Qt
   versions; it does not affect assertions.
5. Source offscreen `--selftest`: **passed** with both system Python and the existing
   build dependencies. `git diff --check`: **passed**.

For the final run, a temporary fixture runtime was read from the ELF prefix of the
already cached `build/tools/appimagetool`, using `find_squashfs_offset`. No tool,
application source or existing distributable was modified to extract it. Reproduce
that setup from the project directory if the same local build environment exists:

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from appforge.core.formats.appimage import appimage_type, find_squashfs_offset
source = Path('build/tools/appimagetool')
assert appimage_type(source) == 2
size = find_squashfs_offset(source)
assert size and size < source.stat().st_size
with source.open('rb') as stream:
    Path('/tmp/appforge-phase7-runtime').write_bytes(stream.read(size))
PY
APPIMAGE_RUNTIME_FILE=/tmp/appforge-phase7-runtime \
PYTHONPATH=src:.venv-build/lib/python3.14/site-packages \
QT_QPA_PLATFORM=offscreen python3 -m pytest -q -ra
```

The Python 3.14 site-packages path above describes this verified host only. On a
normal development installation use the Python environment with
`requirements-dev.txt` installed, and a compatible local runtime or allow
appimagetool's normal runtime download. No packages were installed in this task.
Tiny temporary test AppImages were built; no AppForge distributable was built.

## Files changed

- `src/appforge/core/updates/installer.py`: connection-failure descriptor cleanup.
- `tests/test_integration.py`: 12 integration/safety cases.
- `tests/conftest.py`: explicit socket-permission capability fixtures.
- `tests/make_fixtures.py`: offline runtime option and fixture error diagnostics.
- `tests/test_core.py`: real AppImage launch tests without FUSE.
- `tests/test_phase5.py`: current self-hosted provider contract; TCP probe.
- `tests/test_updates.py`: TCP probe for existing HTTP fixture.
- `tests/test_v053.py`: Unix-socket probe for real process handoff.
- `README.md`: development checks and test requirements.
- `docs/PHASE_7_PLAN.md`: plan, evidence, limits and remaining checks.
- Local `roadmap.md`: Phase 7 status; remains excluded from publication.

## Remaining acceptance checks

Phase 7's automated implementation is ready, but full desktop acceptance is not
claimed. Run the suite on an unrestricted Linux host and resolve any failures;
all 12 socket-dependent tests should execute there. Verify live provider access,
release downloads and process activation. Real KWin/D-Bus, tray menus, login startup,
notifications and desktop launcher appearance need desktop verification.

Build/test the final AppImage on CachyOS/KDE Plasma in light and dark modes:

- Fresh temporary library and an upgrade from a backed-up existing library.
- Add/drop/discover; details, notes, categories/search/sort and file reconnection.
- Single and batch updates, cancellation, backups/rollback and selected cleanup.
- Export/import and restart; preserve settings, menu integration and shortcuts.
- Minimize/close/restore through the tray, background actions and notifications.
- Start at login/start hidden, second-instance activation and self-update/restart.

Prior user confirmation of the 0.5.9 Plasma fix is preserved as prior evidence;
it does not substitute for testing this changed source. The user has confirmed
**0.6.0** as the working version. Project version declarations, README, discovery
guide and roadmap now agree, and `releases/RELEASE_NOTES_v0.6.0.md` includes the
shared-category change and failed-download cleanup fix. Previous version: 0.5.9.
Earlier notes are preserved; no publication date was inferred. A matching 0.6.0
AppImage still needs building and manual testing before publication. No staging,
commit, push or publication occurred; `.git` remains read-only in this environment.

### Confirmed 0.6.0 source preparation

Updated `pyproject.toml`, `src/appforge/__init__.py`, README badge/current-feature
section, `docs/DISCOVERY.md` heading, `docs/CATEGORIES.md`, this report and local
roadmap. Created only the matching public
`releases/RELEASE_NOTES_v0.6.0.md`; it documents shared categories, legacy behavior,
category-dropdown repair, failed-download descriptor cleanup and upgrade guidance.
No release date was supplied or added. All ten historical release-notes files were
SHA-256 checked and remain unchanged. Historical feature versions and fixtures
remain unchanged.

Fresh validation after the version update: **483 passed, 12 skipped, one existing
Qt deprecation warning**, no failures/errors, using the previously documented local
runtime/build dependencies. Source smoke, active-version/notes-heading consistency
and whitespace checks passed. The socket skips retain the limitations described
above. No `dist/AppForge-0.6.0-x86_64.AppImage` exists in this workspace. SOURCE is
ready for the user to build and manually test that matching binary; publication
is not ready until that is completed and explicitly confirmed. No binary was
built, renamed or modified, and no Git metadata or remote state was written.


## Library layout follow-up for 0.6.0

Plan: reuse the existing fixed-size AppCards and FlowLayout, center the occupied
columns with consistent alignment for incomplete rows, and calculate a four-card
startup width from the card size, gaps and outer margins. Preserve larger saved
windows and saved height/state; cap startup sizing to the current screen. Hide
library scrollbars using Qt policies, retaining wheel/trackpad scrolling. Change
only main-window/layout code, regression tests, README and 0.6.0 notes; add no
dependencies or persistent settings. Validate startup with saved geometry, smaller
screens, row alignment and wheel scrolling, then inspect light/dark layouts.

Implemented in `ui/main_window.py` and `ui/flow_layout.py`, with three layout
regression cases in `tests/test_library_layout.py`. Four-card startup is 1478
logical pixels with the current 340-pixel cards, 18-pixel gaps and 32-pixel outer
margins. It also expands older narrow saved geometry, respects smaller screens,
and retains larger window widths. The centered grid keeps incomplete rows aligned
to the first column. Hidden Qt scrollbars retain normal wheel/trackpad scrolling.

Validation: **486 passed, 12 skipped**, with the same prohibited TCP/Unix sockets
and existing Qt constructor warning. The layout checks exercise four columns,
equal gutters at multiple widths, partial rows, old saved geometry, smaller-screen
wrapping and actual wheel-event scrolling. Source smoke and whitespace checks
passed. Light/dark main-window screenshots with 17 apps were visually inspected;
both had equal side margins and no visible scrollbars while content overflowed.
No database migration, dependency, AppImage build or publishing operation.

## Per-application update controls follow-up for 0.6.0

Plan and implementation: reuse application metadata and UpdateService to persist
pause and exact source/tag skip preferences independently of cached check results.
Add card-menu pause/resume, skip and clear-skip signals, a yellow paused badge in
both themes, and consistent details, filter, notification, tray-count and update
eligibility behavior. Pause excludes manual/startup/scheduled checks; skip keeps
checks enabled for future releases. Guard changes during checks and queued/running
updates. Preserve existing user changes, version 0.6.0 and every dist artifact.
No dependency or database migration; preferences stay local to this installation.

Changes: `core/update_policy.py`, `core/updates/service.py`, `core/organize.py`,
`ui/app_card.py`, `ui/main_window.py`, `ui/details_dialog.py`, `ui/theme.py`, and
`tests/test_update_controls.py`. README, `docs/UPDATE_CONTROLS.md`, roadmap and
`releases/RELEASE_NOTES_v0.6.0.md` describe the controls.

Validation: 11 new regression cases cover database reopen persistence, exact
source/tag matching, newer releases, pause/resume/clear-skip interaction, card
menus, details actions, tray counts, notifications, check selection, direct and
batch installation guards, busy-state guards and missing-file repair. Full suite
with the existing build dependencies and an offline fixture runtime: **497 passed,
12 skipped**, with one existing Qt deprecation warning. The documented command
above was reused with `/tmp/appforge-update-controls-runtime` as the temporary
runtime. Eleven skips require prohibited TCP sockets; one requires Unix sockets.
The initial system-only run reported 475 passed, 2 skipped and 31 setup errors
because appimagetool could not download its runtime; the offline setup resolved
those errors. Source offscreen smoke test and `git diff --check` passed. Paused and
skipped cards were rendered and visually inspected in light and dark themes.

SOURCE is ready to build and manually test as AppForge-0.6.0-x86_64.AppImage.
No AppForge distributable was built or modified, and no commit, push or publishing
operation was performed. Manual desktop/AppImage approval remains pending.

## Appearance toggle follow-up for 0.6.0

Plan and implementation: extend existing AppSettings with a validated theme mode
(system by default, explicit light/dark after toggling). Reuse the existing theme
palettes and application stylesheet for immediate changes across open windows.
Add a header tool button directly after Settings with matching dimensions, blue
styling, keyboard access and an accessible action label. Render sun/moon icons
at 1x/2x/3x for sharp HiDPI display. In dark mode show a sun to switch to light;
in light mode show a crescent moon to switch to dark. Retint header icons when
appearance changes, and respect the saved override when the desktop theme changes.
Do not rebuild cards, restart workers or reset search/filter/scroll state.

Files: `core/settings.py`, `ui/theme.py`, `ui/icons.py`, `ui/main_window.py`,
`app.py`, `tests/test_theme_toggle.py`, README, roadmap and the existing public
0.6.0 notes. No new dependencies or database migration. Version remains 0.6.0.

Validation: four new cases cover preference defaults/validation/database reopen,
button placement and icon alternation, live switching with unchanged card and
busy/search state, recoloring an already open dialog, startup restoration and
explicit preferences overriding desktop theme changes. Focused existing layout,
update-controls and favorites checks: 23 passed. Source offscreen smoke and
whitespace checks passed. Full main-window renders were visually inspected in
light and dark themes; button placement and both icons are correct.

Final full-suite result using the documented offline fixture runtime and existing
build dependencies: **501 passed, 12 skipped**, one existing Qt deprecation warning.
The skips cover 11 prohibited TCP socket cases and one Unix socket/process-handoff
case. No failures or errors. SOURCE remains ready for the user to build and
manually test AppForge-0.6.0-x86_64.AppImage; no distributable, Git metadata or
remote publication was changed.

## Consistent card badges for 0.6.0

Plan and implementation: reuse the existing chip selectors in `ui/theme.py` to
apply the paused badge's visual treatment across statuses and format chips:
soft tinted fill, one-pixel colored outline, matching text, and shared rounded
shape/padding. Preserve green success, blue update/format, yellow paused, red
failure/file warnings and gray neutral states. No application logic, version,
database or binary changes. README and the existing 0.6.0 notes describe it.

Visual QA: rendered eight representative cards in light and dark mode, covering
up to date, update available, paused, failed, no source, skipped, missing and not
executable. Verified consistent outlines, tinted fills, readable labels and no
card overflow. Source offscreen smoke test and `git diff --check` passed.
Focused update-controls, appearance-toggle and library-layout regression checks:
**18 passed**. Existing dist AppImages remain untouched; matching 0.6.0 binary
build/manual testing is still the user's next step.

## Advanced launch options follow-up for 0.6.0

Plan and implementation: introduce shared Qt-free launch-option validation in
`core/launch_options.py`, store configuration in existing application metadata,
and reuse it for the detached launcher and managed desktop entries. Add optional
command-line arguments, an absolute/custom working directory and Run in terminal.
Parse arguments with shell-style quoting but launch with an argv list and no
shell. Default arguments remain empty and the default directory remains the app's
folder. Terminal launches prefer the desktop terminal helper, then known terminal
emulators with a KDE/Konsole preference. Desktop entries use Terminal=true and
retain existing app IDs, environment preferences and embedded file/URL markers.
Validate missing/inaccessible folders at launch and display user-readable errors.

Expose a Launch options dialog from both Add and Edit; options stay local until
the parent dialog saves, and canceling discards edits. Support resetting defaults.
Make Add/Edit bodies scroll with fixed footers to keep all controls accessible on
small screens. Wrap long hints so the new scroll containers do not clip fields
horizontally. Preserve existing user changes and version 0.6.0; no migration or
new dependency. Launch options participate in validated library export/import and
survive metadata refresh, updates and rollback.

Files: `core/launch_options.py`, `core/library.py`, `core/library_transfer.py`,
`core/desktop/service.py`, `services/launcher.py`, `ui/launch_options_dialog.py`,
`ui/dialogs.py`, `tests/test_launch_options.py`, README,
`docs/LAUNCH_OPTIONS.md`, `docs/LIBRARY_TRANSFER.md` and the existing public
0.6.0 release notes. The optional local roadmap file was unavailable for this
follow-up; no replacement was created.

Validation: 31 new test cases cover literal/quoted/empty arguments, invalid
configuration, actual process argv/cwd/environment delivery without shell
expansion, default/missing/inaccessible directories, terminal selection and
command separators, desktop quoting/percent markers, persistence across database
reopens/update/rollback, transfer round trips, dialog validation and folder
picker, cancel/save semantics and scrollable forms with reachable footers.
The full suite after initial implementation: **531 passed, 12 skipped**, one
existing Qt deprecation warning, using the previously documented offline fixture
runtime and build dependencies. After the final hint-wrapping and folder-permission
handling changes plus their regression case, focused launch-options, GUI,
categories, layout, desktop/environment and transfer suites: **174 passed,
2 skipped**. Skips require prohibited TCP/Unix socket capabilities. Source
offscreen smoke and `git diff --check` passed. Add, Edit and Launch options were
rendered and visually inspected in light and dark mode.

Native terminal windows and desktop activation still need manual verification on
the user's desktop (including KDE/Konsole). Terminal process handoff may prevent
AppForge's existing log/early-exit check from reporting the child app's output or
exit status; this is documented in the user guide. No matching AppForge binary
was built, renamed or modified. SOURCE is ready for the user to build and manually
test AppForge-0.6.0-x86_64.AppImage; no Git metadata or remote state was written.
