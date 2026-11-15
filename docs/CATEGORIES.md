# Shared application categories in AppForge 0.6.0

## Implementation plan

Use the existing noneditable KDE/freedesktop category dropdown as the only Category
control in Add/Edit. Reuse `MENU_CATEGORIES` and the existing `menu_category` metadata
rather than adding a setting or schema migration. Library grouping/search/filtering
must prefer that selected category, with the same display labels as the dropdown.
Saving a category in Edit clears the superseded library-only override.

Preserve older custom categories when no desktop category was selected and the
user saves unrelated edits. Map recognizable legacy standard categories to the
shared desktop category; arbitrary legacy names remain readable until the user
chooses a replacement. An existing explicit desktop category takes precedence when
old records contain conflicting values. Automatic continues to use embedded
metadata, with Other for unclassified files in AppForge.

Affected files: core desktop category resolution, core organize category labels,
Add/Edit dialogs, category regression tests, README and this guide. Reuse existing
launcher synchronization, library refresh and JSON transfer. No extra dependencies,
KDE configuration changes, schema migration or binary build. Validate popup
selection, saved launcher contents and library filters, legacy records, restart,
transfer and automatic reset; inspect both themes and run full regression/smoke.

## Using the shared category

In Add or Edit, select **Category** and save. AppForge uses the choice for category
filters and category searches, even if **Add to the application menu** is disabled.
When menu integration is enabled, the same choice updates the existing launcher;
its desktop-file ID remains unchanged, preserving pinned shortcuts. **Automatic**
removes your explicit choice and uses the embedded application metadata.

The dropdown uses the existing standard desktop categories and their display
names, including Games, Internet, Multimedia, Science & Math, and Utilities. It
does not discover custom or renamed sections from a user's Plasma menu setup.
Unclassified automatic entries continue to appear under Other in AppForge.

Existing explicit desktop categories win over old library-only overrides. Existing
standard library categories (for example Games) are recognized in both places and
converted to the shared setting when Edit is saved. Arbitrary custom library
categories remain available for filtering until you select a replacement. The
Edit dialog explains this for those entries; explicitly selecting Automatic also
clears an old custom category. Cancelling changes preserves the original record.

## Validation and scope

- **27 new category tests passed**, including clicking a real popup item, all
  standard labels, Add without desktop integration, Edit, cancellation, reset,
  legacy records, filtering/searching, restart, transfer and invalid stored values.
- Full suite with the existing build dependencies and local fixture runtime:
  **483 passed, 12 skipped, no failures/errors**. The skips are the same 11 real
  TCP tests and one Unix process-handoff test blocked by this environment. The
  existing Qt drag-event constructor warning remains.
- Offscreen source smoke test and whitespace checks passed. Edit layouts were
  rendered and visually inspected in light and dark; the dropdown popup was also
  inspected. Actual Plasma menu placement remains a manual desktop check.
- Changes: `core/desktop/service.py`, `core/organize.py`, `ui/dialogs.py`, new
  `tests/test_categories.py`, the existing Edit category test in `tests/test_gui.py`,
  README and this guide. Earlier Phase 7 work remains preserved.
- No new database migration or runtime dependency. The user subsequently confirmed
  0.6.0 as the working version; active declarations and matching public release
  notes now include this change. No AppForge binary build or publishing operation.
