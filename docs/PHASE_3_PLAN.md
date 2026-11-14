# Phase 3: release notes viewer

## Plan

Extend the shared Release model and GitHub/GitLab/Forgejo mappings with release
bodies. Carry the exact selected release through CheckOutcome into the existing
JSON metadata store; no database migration. Add a read-only exact-tag fetch helper
and a modeless Qt viewer, using background workers and main-thread cache writes.
Reuse card/details action routing. The existing single-update flow starts directly;
no extra confirmation is introduced. The Update All confirmation will offer notes
before its existing approval.

Cache identity includes repository and tag. Successful update checks replace the
cache, including empty descriptions; failed checks retain it. Viewer refresh must
never substitute a different release or change update/install state. Discard stale
results after source/tag changes, removal or closure. Render Markdown with remote
images disabled and allow only HTTP(S) browser links. Preserve Python 3.10+, themes,
provider token routing, existing records, installer and rollback safeguards.

Validation: provider payload fixtures, cache persistence/invalidation, exact-tag
errors, asynchronous GUI routing/lifetime and read-only checks; focused regression
suite, full suite, source selftest, and light/dark visual inspection. Existing
AppImages remain untouched. Version finalization requires confirmation under the
permanent release workflow.

## Implementation and validation

Implemented in `core/updates/notes.py`, `ui/release_notes_dialog.py`, shared
Release/provider/checker/service mappings, and card/details/main-window routing.
Tests are in `tests/test_release_notes.py`. README and the local roadmap describe
the workflow. Confirmed version advances from 0.5.6 to 0.5.7 in `pyproject.toml`,
`src/appforge/__init__.py`, README and roadmap; public notes are
`releases/RELEASE_NOTES_v0.5.7.md`. Historical release files remain unchanged.

- Focused release-notes/details/source/discovery/backup/GUI/publishing suite:
  **137 passed**, including **23 release-notes cases**.
- Full suite: **268 passed, 3 failed, 31 setup errors; no skips**. The same three
  failures are the previously recorded injected-client expectation in
  `test_phase5.py`, socket-based executable installer test there, and
  single-instance socket test in `test_v053.py`. All 31 setup errors arise while
  appimagetool builds shared fixtures. No new failure category was observed.
- Source `--selftest`: passed with the offscreen Qt platform.
- Light/dark release-note layouts rendered and visually inspected; long notes
  open at the top and retain scrolling across library refreshes. Links use the
  theme palette. Worker closure/source/tag/removal races are tested.
- Provider parsing is verified with offline payloads for GitHub, GitLab,
  Codeberg, self-hosted Forgejo/Gitea and GitLab fallback. Live API/network testing
  and manual desktop/AppImage testing remain pending.

No schema migration, build, commit, push or upload. Existing `dist/` files were
not modified. Source is ready for the user to build and manually test
`AppForge-0.5.7-x86_64.AppImage`; publication is not yet approved. Git metadata is
read-only in this environment.

## Changed files

- Provider/cache logic: `src/appforge/core/updates/github.py`, `providers.py`,
  `checker.py`, `service.py`, and new `notes.py` in that directory.
- UI: `src/appforge/ui/app_card.py`, `details_dialog.py`, `main_window.py`, and new
  `release_notes_dialog.py` in that directory.
- Tests: new `tests/test_release_notes.py`.
- Versions/documentation: `pyproject.toml`, `src/appforge/__init__.py`, `README.md`,
  `docs/DISCOVERY.md`, this plan, and `releases/RELEASE_NOTES_v0.5.7.md`.
  The local-only `roadmap.md` also records completion and verification limits.

## Continuing 0.5.7 development

The user confirmed the release-notes viewer works, then requested Phase 4 in the
same 0.5.7 update. The current combined scope and validation are recorded in
`docs/PHASE_4_PLAN.md`; the existing 0.5.7 public release notes now cover both
phases. Earlier validation counts above describe Phase 3 at its completion. The
user subsequently reported manual testing passed; the matching binary identity
and refreshed release-preparation checks are recorded in `docs/PHASE_4_PLAN.md`.
