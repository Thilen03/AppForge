# Per-application update controls

Open the three-dot menu on an application card to manage its updates.

## Pause updates

Choose **Pause updates** to stop startup, scheduled and manual update checks for
that app, and to prevent both individual updates and Update All. Its normal
update badge becomes a yellow **Update paused** badge, with colors adapted to
light and dark themes. Details also shows Update paused. Choose **Resume updates**
to enable updates and immediately request a fresh check when a source is linked.
You can pause an app before linking an update source.

A missing file or missing executable permission still shows its repair warning
on the card. Pausing does not change launching, desktop launchers, backups or
rollback. It applies to the selected library app, not TuxShelf's own self-update.

## Skip this version

When an update or retry is available with an identified release tag, choose
**Skip this version**. The card shows **Version skipped** and hides its update
button. Update All, update notifications and available-update counts exclude it.
Checks continue: a different release tag is eligible as usual. A skip is tied to
the exact source URL and release tag, not a version range or permanent version pin.
A different update source is unaffected even if it uses the same release tag.

Choose **Clear skipped version** to undo the stored skip. If a newer release has
already been found, clearing the skip does not change that newer release.
Pausing and resuming preserves the skipped release choice.

## Persistence and operations

Both choices are stored in the existing local application metadata and survive
restarts without a database migration. They are not included in library exports.
Cached release details and notes are retained; a paused app's cached latest
version may be out of date until checks resume.

Controls are disabled while the app is checking, queued for an update or updating.
Let the operation finish before changing them. Pausing does not interrupt an
installation already in progress.
