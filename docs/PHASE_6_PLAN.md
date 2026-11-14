# Phase 6 — Enhanced system tray

## Preparation and implementation plan

Reuse the Phase 0 architecture review, existing TrayController, MainWindow update
workers/confirmation dialog, launcher environment handling, AppSettings and
UpdateService notification markers. SQLite stays on the UI thread. No schema,
installer, dependency or backup changes are needed.

- Extend `ui/tray.py` with update count/activity, navigation, Update All,
  Favorites, Recently used, all application shortcuts and favorite selection.
- Store shortcut IDs in the existing global settings table via `core/tray.py`;
  record successful launch requests and ignore removed IDs. Do not export usage.
- Connect existing workflows in `ui/main_window.py`; refresh status after changes
  and progress, and rebuild shortcuts when opening the menu. Keep launch errors
  and update confirmation accessible from a hidden window.
- Respect notification preferences; summarize hidden batch completion once,
  distinguish failed checks from up-to-date results, and retain once-per-version
  availability notifications. Preserve close-to-tray and explicit quit behavior.
- Test with script entries and fake workers/trays (no network or AppImage needed),
  run regression checks and source smoke test, and inspect light/dark menus.

Risks: desktop tray support varies; native host rendering requires manual desktop
verification. Tray failures must fall back to the main window. Recent launches
mean launches requested successfully through AppForge, not external desktop use.

## Implemented behavior and validation

Development version: 0.5.8 → 0.5.9. Phase 6 only; Phase 7 remains planned.

Changed files: `src/appforge/ui/tray.py`, `src/appforge/ui/main_window.py`,
`src/appforge/core/tray.py`, `tests/test_tray.py`, `pyproject.toml`,
`src/appforge/__init__.py`, `README.md`, `docs/DISCOVERY.md`, this plan,
local `roadmap.md`, and `releases/RELEASE_NOTES_v0.5.9.md`.

- 19 tray tests passed, covering shortcut preference persistence/corruption, missing
  and removed apps, duplicate names, ID routing, launch environment preservation,
  successful/failed launch recording, status/progress, navigation, actual Update All
  confirmation/batch queuing, hidden success/failure/cancellation notifications,
  preferences, notification deduplication, optional tray failures and explicit exit.
- Focused regression run: 227 passed across tray, storage, details, release notes,
  transfer, discovery, backups, GUI and publishing tests.
- Final full suite: 365 passed, 3 failed, 31 setup errors. Failures remain the recorded
  provider expectation mismatch (`test_checker_routes_by_provider_and_uses_injected_client`)
  and restricted sockets (`test_install_executable_update_validates_backs_up_with_bak_suffix`,
  `test_second_launch_signals_first_and_exits`). Setup errors come from the shared
  appimagetool fixture generation, matching the previous phase's restrictions.
- Source startup smoke test passed with the offscreen Qt platform. Whitespace checks
  passed. Root menu, favorites, recents and favorite selection were rendered and
  visually inspected with both light and dark palettes.

No schema migration: `tray_favorites` and `tray_recent` store JSON ID lists in the
existing global settings table. App records, credentials, backup workflows and
library transfer format remain intact. Identical background-check errors are
suppressed within the current session, while availability markers remain persistent.
Shortcuts refresh from current records when opening the tray menu; update status
and progress refresh during operations without rebuilding open submenus.

Native desktop tray hosting, compositor activation, real background downloads and
manual AppImage verification remain pending. No AppImage was built or modified.
Source is ready for the user to build and manually test; release publication has
not been requested or performed. Git metadata remains read-only in this environment;
no staging, commits or publishing were attempted.

## Library favorites follow-up (same 0.5.9 update)

The user confirmed the tray work functions and requested favorites in the main
library without another version bump. Reuse TrayShortcuts and its existing
`tray_favorites` setting as the single source of truth, connect card menu changes
to the same handler as the tray, and reload cards after either entry point changes
favorites. Stable partitioning of the existing sorted list puts favorites first
without changing filters or ordering within each group. AppCard accepts a favorite
flag and paints a small gold star in the title row, reserving name space for it.
No schema change, export change, binary build or publication.

Files: `ui/app_card.py`, `ui/main_window.py`, `tests/test_favorites.py`, README,
these preparation notes and the existing 0.5.9 public notes. Preserve all prior
Phase 6 work. Validation covers all three sort modes, card/tray synchronization,
star/menu state, persistence, no-tray operation and filters/progress during reload.

Follow-up validation: 36 focused favorites/tray/details/GUI tests passed, including
six new library-favorites cases. Source smoke test and whitespace checks passed.
Favorite/non-favorite cards with long names were rendered and visually inspected
in light and dark themes. Styled font metrics now reserve enough room for the star
and elide long titles cleanly. Version declarations remain 0.5.9. Native desktop
verification of this follow-up remains for the user; existing AppImages are untouched.
The full-suite result above predates this follow-up and was not rerun.

## Rounded star and direct favorite action (still 0.5.9)

Replace the painted marker in `ui/app_card.py` with a compact accessible button:
keep the 18px footprint, increase the star's body thickness and round tips/inner
corners with quadratic curves. Reuse the existing favoriteRequested signal for
mouse/keyboard toggles and the existing card hover/focus reveal logic for the gray
non-favorite star. Keep gold favorites visible, reserve the same title space while
hidden to avoid layout movement, and consume double clicks to prevent launches.

Updated `tests/test_favorites.py`, README and the existing public 0.5.9 notes.
Validation: 39 focused favorites/tray/details/GUI tests passed, including mouse
toggling and tray synchronization, stable layout/visibility, Space activation and
protection against accidental card launches on double-click. Source smoke test and
whitespace checks passed. Hovered gray and gold stars were rendered and visually
inspected in light and dark themes. No full-suite rerun or AppImage build; version
remains 0.5.9 and existing binaries remain untouched.

## Minimize-to-tray and login startup plan (same 0.5.9)

Reuse the background preference and tray capability checks for close/minimize;
defer the hide until Qt finishes its window-state event and recheck the state so
restore requests cannot race with it. Exiting remains explicit. Add per-user XDG
autostart management in `core/autostart.py`, using existing launcher argument
quoting and stable AppImage/source commands, atomic file replacement, and ownership
checks before modifying/removing an entry. Add login/start-hidden preferences to
AppSettings and SettingsDialog with dependency controls and visible save errors.
Bootstrap distinguishes login launches from normal launches, preserves
single-instance activation and falls back to a visible window when no tray exists.
Repair enabled startup entries when the running installation moves. Keep Settings
usable on shorter screens with scrolling. Tests will isolate configuration files
and cover command quoting, ownership, failures, preference persistence, minimize /
restore / exit and startup with and without a tray. No migration or version bump.

### Startup/minimize implementation and verification

Implemented in `core/autostart.py`, `core/settings.py`, `ui/settings_dialog.py`,
`ui/main_window.py` and `app.py`; tests in `tests/test_autostart.py`. Updated README,
the existing 0.5.9 notes and local roadmap. `start_at_login` and `start_minimized`
use existing settings rows, default off; no schema migration. Existing installations
keep their background preference, now applied equally to minimize and close. The
start-hidden control implies background mode, and no-tray startups fall back to a
visible window. The autostart command is marked `--autostart` so ordinary launches
still open normally. Duplicate login launches do not activate a running instance.
Self-update prompts are deferred while hidden and offered on opening the window.

The Qt-free autostart service reuses stable AppImage detection, source launch argv
and desktop Exec quoting. It atomically writes only its own regular per-user entry,
rejects symlinks and unrelated files, and reports permission/configuration errors.
Enabled entries refresh at startup after an AppImage move. No user login entry was
enabled during development; tests use isolated temporary XDG config directories.
Reference: [Desktop Application Autostart Specification](https://specifications.freedesktop.org/autostart/latest/).

Validation: 53 initial focused startup/tray/favorites/GUI tests passed. The full
suite reported 395 passed, 3 failed and 31 setup errors, with the same provider
expectation mismatch, socket restrictions and appimagetool fixture errors documented
above. An additional save-path check ensures failed autostart writes do not partially
save token changes; after that adjustment, 170 regression tests passed with the two
known provider/socket tests explicitly deselected. Source smoke test passed. Settings
was rendered and visually inspected in light and dark, including a reduced-height
layout with scrolling. Native taskbar/desktop login behavior still needs manual
AppImage testing. Version remains 0.5.9; existing dist files are untouched.

## Tray menu and native minimize follow-up plan (0.5.9)

Remove the duplicate Open application library action, signal and handler while
preserving Open AppForge and its existing filter state. The previous offscreen
checks only exercised QWidget.showMinimized. Add regression cases for native
QWindow minimization when QWidget callbacks are missed or widget state lags.
Connect native window state/visibility signals on show, coalesce deferred minimize
handling with a cancellable timer, and hide both widget and native surface while
clearing the minimized flag after hiding. Keep background/tray/quit guards; cancel
pending hide when restoring. Check repeated cycles, restore races, and existing
no-tray, background-disabled, startup and exit behavior. Update the existing notes
and README. Native Wayland probe aborts in this environment, so do not claim native
compositor/taskbar verification from the offscreen tests.

### Native minimize follow-up results

Removed the redundant library menu action, signal and filter-reset handler from
`ui/tray.py` and `ui/main_window.py`; Open AppForge remains. Updated
`tests/test_tray.py`, `tests/test_autostart.py`, README and the existing 0.5.9 notes.
The five new cases cover missed widget callbacks, delayed widget state, four
native minimize/restore cycles, restore-before-hide cancellation, and native
minimize with background disabled. The first two failed against the previous
implementation. The repeated-cycle test additionally exposed stale native minimized
state after hiding; both native and widget states are now explicitly cleared.

A single-shot Qt timer coalesces widget and native signals; restoring cancels it.
Native signals are connected once per window handle on show. Minimize and close
share the guarded hide helper, which unmaps both the widget and native window,
without changing background preferences, timers or update jobs.

Validation: 65 focused tests passed; full suite 400 passed, 3 failed and 31 setup
errors. Failures remain the documented provider expectation and restricted socket
tests; setup errors remain the shared appimagetool fixture failure. Source smoke
test and whitespace checks passed. Updated tray menus were rendered and inspected
in light/dark themes. Version stays 0.5.9; no binary build or publication.

Verification limit: native Wayland startup for an isolated probe aborted in this
environment. The native QWindow tests use Qt's offscreen backend, not a real desktop
compositor. Real titlebar/taskbar behavior still needs manual testing with the new
AppImage. Minimize events wholly withheld by a Wayland compositor cannot be inferred
from focus loss (and focus loss must not be treated as minimization). See Qt's
[QWindow state/visibility API](https://doc.qt.io/qt-6/qwindow.html) and the
[XDG shell protocol](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/stable/xdg-shell/xdg-shell.xml).

## KDE Plasma minimize follow-up plan (0.5.9)

The user confirms the issue persists on CachyOS/KDE Plasma. The prior native Qt
callbacks cannot cover compositor minimization that Wayland does not report to
the application. Add an optional `ui/kwin_tray.py` session-only KWin bridge for
Plasma's Wayland backend: load a temporary script over QtDBus, listen only to this
process's normal AppForge window, and forward actual minimized/unminimized state
to the existing guarded hide helper. Do not infer minimization from focus/exposure.
Use async D-Bus, ownership-specific script names and a private callback path/token;
unload and remove the temporary script when background mode is disabled or AppForge
exits. Preserve native Qt behavior for other desktops/backends. Handle missing,
denied, restarted or disconnected D-Bus/KWin without crashing. Ensure QtDBus is
bundled, exercise generated JS with a simulated KWin workspace and test lifecycle /
no-Qt-event routing. No source version bump, AppImage build or KDE configuration edits.

### Plasma-specific implementation and validation

Added `ui/kwin_tray.py` and `tests/test_kwin_tray.py`; connected the bridge to
`ui/main_window.py` and included QtDBus explicitly in `packaging/appforge.spec`.
Updated README, public 0.5.9 notes and local roadmap. The existing Qt event paths
remain for other desktops and X11. No migration, dependency package addition,
version bump or KDE configuration change.

The bridge uses the KDE session bus unique destination, a random per-session
callback path/token and a process-scoped script name. Its script checks the window
PID and normal-window/dialog flags, observes current and newly mapped windows, and
forwards KWin's actual minimized boolean to the existing guarded hide helper. It
never infers minimization from focus loss or changes compositor window properties.
Load/run/unload use asynchronous QtDBus calls with timeouts and service auto-start
disabled. Stopping removes the callback and temporary file and unloads only its own
script. Stale load/run completions cannot restart a disabled observer or remove a
new session. KWin owner changes reconnect an enabled bridge; missing/denied bus,
registration, script and filesystem failures are logged and surfaced in the status
bar. A hard crash can leave an inert observer until KWin restarts; it points to the
old unique bus destination and cannot affect other apps. No persistent script is
installed or enabled for future sessions.

Validation: 22 bridge tests passed; 87 focused Plasma/startup/tray/favorites/details/
GUI tests passed. Tests execute generated observer JavaScript in QJSEngine against
a simulated KWin workspace, exercise real QtDBus completed reply/error handling,
and route a compositor callback while Qt's window remains non-minimized. Lifecycle
checks cover load/run failure, disabling during load, stale completion, service
restart, callback token validation, unrelated windows and quit cleanup. The full
suite reports 422 passed, 3 failed and 31 setup errors, matching the recorded
provider expectation/socket and appimagetool-fixture restrictions. Source smoke and
whitespace checks passed.

Real KWin/D-Bus end-to-end verification is blocked: an isolated dbus-run-session
fails to bind its Unix socket with Operation not permitted, and the earlier native
Wayland probe aborted. These mocks and offscreen tests are not a claim of testing
KDE's titlebar on CachyOS. Source is ready for the user to build and manually test.
Exit any old AppForge instance through the tray first: an ordinary second launch
activates the running instance, so rebuilding 0.5.9 without exiting can test the
old process. No AppImage was built, changed or published during this work.

References: [KDE scripting API](https://develop.kde.org/docs/plasma/kwin/api/) and
[KWin scripting source](https://sources.debian.org/src/kwin/4:6.3.6-1/src/scripting/scripting.cpp/).

## 0.5.9 release preparation

Previous released source: **0.5.8**, commit
`7a5cdb0b9cbb66905f845aa0d1c1bc53d972c3a6`. User-confirmed prepared version:
**0.5.9**. Both project version declarations, README, discovery-guide heading,
local roadmap, matching public notes heading and selected asset filename agree.
No further version increment or publication date was added.

Reviewed source diffs/history since the previous release and the implemented
tray controls, shared favorites/stars, login startup/start hidden, background
notifications and KDE Plasma minimize handling against source and tests. Public
notes now use normal-user language, with installation/upgrade instructions and
only nonempty sections. README links the 0.5.9 notes and lists startup in Settings.
The user reports that the final KDE fix worked on CachyOS/Plasma. This updates the
previous native-verification limitation for that reported behavior; it does not
claim the user tested every feature or independently identify the tested binary.

Preparation modified only README, `releases/RELEASE_NOTES_v0.5.9.md`, this plan and
local `roadmap.md`. Application source was fingerprinted before/after and remained
unchanged. Earlier release notes were hash-checked and preserved. No schema
migration, application-code change, binary execution, build, staging or publication.
The complete development file list remains in the sections above and Git status.

Selected local asset (regular, non-symlink, nonempty):

- `dist/AppForge-0.5.9-x86_64.AppImage`
- Size: **84,638,200 bytes**
- SHA-256: `b1fae9a96d310b28a8f98a2bba40be5fc7c7999bb08f1c68719a5b1f2a1a90b3`

The asset hash was rechecked after preparation and remains unchanged. No
provenance sidecar was supplied or required. Its filename and size/hash are
verified; automatic source/build provenance is not established. The user confirmed
the KDE fix works, but has not explicitly bound complete manual build/test approval
to this exact hash. The local publishing workflow supplies that final confirmation.
If this file was built from the final application source and already manually
tested, preparation's documentation-only edits introduce no new application code
to rebuild. Otherwise the user builds/tests the matching artifact themselves.

Fresh preparation validation:

- **152 passed** in the focused Plasma/startup/tray/favorites/details/GUI/publishing
  tests, no skips.
- Full suite: **422 passed, 3 failed, 31 setup errors**, no skips. Failures are
  `test_checker_routes_by_provider_and_uses_injected_client` (previous provider
  expectation mismatch), `test_install_executable_update_validates_backs_up_with_bak_suffix`
  and `test_second_launch_signals_first_and_exits` (restricted sockets). Setup
  errors remain shared appimagetool fixture creation failures. The suite is not
  wholly passing and no failing test was hidden or represented as passing.
- Offscreen source `--selftest`: **passed**.
- `git diff --check`: **passed**.
- `./scripts/publish.sh release --dry-run`: **passed**, verifying local
  asset/version/notes and approved-file policy. It did not fetch, stage, commit,
  push, contact GitHub or assume manual-testing approval. No index-only removals
  were proposed. Remote authentication, release/tag availability and published
  source are not verified by the offline run.
- Live repository identity: `/home/thilen/appforge`, branch `main`, upstream
  `origin/main`, origin `https://github.com/Thilen03/AppForge.git`. `.git` is
  mounted read-only; its metadata was not changed or relocated.

SOURCE is ready for build/manual-test verification. Matching binary, source and
public notes are locally prepared, with the above evidence limitations. Nothing
was published. Publication remains a separate local-terminal operation using
`./scripts/publish.sh release`, including remote preflight and PUSH/RELEASE
confirmations. Phase 7 was not implemented as part of release preparation.
