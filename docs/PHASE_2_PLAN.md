# Phase 2: application details

## Implementation

- `ui/details_dialog.py` provides a scrollable, modeless details window for each
  application, opened from the card's **Details…** menu action. Double-click
  launching is preserved. Only one details window per application is opened.
- `core/details.py` reads installed file status/size and backup count/size/date
  without running application files or changing the library.
- `core/backups/service.py` exposes the existing backup discovery logic as a
  read-only function shared by details inspection and backup reconciliation.
  Existing backup management still performs its bookkeeping on the main thread.
- `ui/main_window.py` routes details actions through existing handlers and refreshes
  open details windows after library changes and busy-state changes. Periodic and
  manual refreshes also pick up external filesystem changes.
- Workers receive copied application records. SQLite stays on the main thread;
  generation checks discard results from outdated snapshots. Closing the dialog
  disconnects its lifetime from any remaining read-only filesystem work.

## Compatibility and scope

No schema migration or settings changes. Existing records, launchers, backups,
update validation and rollback behavior are preserved. Metadata is rendered as
plain text. Missing descriptions, versions, dates, inaccessible files and backup
scan failures have explicit fallback text.

Release access opens the existing provider release page. Fetching and rendering
release descriptions inside AppForge remains Phase 3. Backup and rollback actions
open the existing management dialog; their underlying operations are unchanged.

## Validation

Tests in `tests/test_details.py` use scripts rather than built AppImages. They
cover read-only inspection, backup totals, missing files, scan errors, action
routing, busy states, single-dialog behavior, refresh after record changes,
installation bookkeeping, real script rollback, stale worker results and closure
while a worker is active.

Light and dark layouts were rendered and visually inspected. Source smoke test
passed. Full-suite results and environment limitations are recorded in the roadmap.
AppImage build and manual desktop testing remain separate user checks.

The confirmed development version is 0.5.6, following 0.5.5. Active version
declarations and `releases/RELEASE_NOTES_v0.5.6.md` agree. Release source is prepared
for building and testing. No release date has been set; publication remains pending.
No AppImage is currently present in `dist/`. The final matching binary still needs
building and explicit manual testing approval.


## 0.5.6 release preparation checks

Compared the working tree against the previous 0.5.5 release source at `5a2410d`.
The release also contains numbered-nightly filename/comparison fixes, an actionable
prerelease-only status, compact discovery folder selection, and a primary-style
Settings button beside Add Application. The user confirmed the update-source fix
works; that confirmation does not establish testing of a final release binary.

- Focused suite: **114 passed** across `test_details.py`,
  `test_selfhosted_updates.py`, `test_discovery.py`, `test_backups.py`,
  `test_v053_gui.py`, and `test_publish.py`.
- Full suite: **245 passed, 3 failed, 31 setup errors; no skips**. Failures remain
  the provider injected-client expectation in `test_phase5.py`, the socket-based
  executable installer test there, and the single-instance socket test in
  `test_v053.py`. Setup errors occur when appimagetool builds shared fixtures.
- `PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m appforge --selftest` passed.
- Light/dark details, discovery selection and Settings layouts were inspected
  during development. Whitespace validation passed.
- No application database migrations, builds, commits, pushes, or uploads were
  performed during release preparation. Git metadata is read-only in this
  environment; publication uses the existing local terminal workflow.

### Changed files for this release

- Versions/documentation: `pyproject.toml`, `src/appforge/__init__.py`, `README.md`,
  `docs/DISCOVERY.md`, `docs/PHASE_2_PLAN.md`, and
  `releases/RELEASE_NOTES_v0.5.6.md`. The local roadmap was also updated.
- Details: `src/appforge/core/details.py`, `src/appforge/ui/details_dialog.py`,
  `src/appforge/core/backups/service.py`, `src/appforge/ui/app_card.py`, and
  `src/appforge/ui/main_window.py`.
- Update checks: `src/appforge/core/formats/appimage.py`,
  `src/appforge/core/updates/checker.py`, `src/appforge/core/updates/service.py`,
  and `src/appforge/core/updates/version.py`.
- Visual refinements: `src/appforge/ui/discovery_dialog.py`,
  `src/appforge/ui/theme.py`, and the main-window changes listed above.
- Tests: `tests/test_details.py`, `tests/test_selfhosted_updates.py`, and
  `tests/test_v053_gui.py`.
