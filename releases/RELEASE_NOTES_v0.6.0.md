# TuxShelf 0.6.0

## New features

- Advanced launch options in Add and Edit let you set command-line arguments,
  choose a working directory and run apps in a terminal. The same preferences
  apply to TuxShelf, tray and desktop-menu launches, survive updates and rollback,
  and are included in library export/import.
- Switch between light and dark mode using the sun/moon button to the right of
  Settings. The whole app changes immediately, and your choice is remembered
  across restarts. The icon shows the mode you can switch to.
- Pause updates for individual apps from the card's three-dot menu. A yellow
  Update paused badge replaces the usual update status. Resume updates from the
  same menu when you are ready.
- Skip an available version while continuing to check for newer releases, or
  clear the skipped version to make it available again. Paused apps and skipped
  releases are excluded from Update All, update counts and update notifications.
- Pause and skip choices are remembered across restarts. Launching your apps and
  restoring backups remain available.

## Improvements

- Add and Edit forms scroll on smaller screens while their Save/Cancel buttons
  remain visible.
- Application-card badges now share a consistent soft tinted background, colored
  outline and matching text, while keeping each status's green, blue, yellow,
  red or gray color in both light and dark mode.
- The library opens wide enough for four cards on screens with enough room and
  balances the spacing on either side of the card grid. Smaller screens still
  wrap cards to fit, and larger saved window widths are retained.
- Library scrollbars are hidden for a cleaner view. Mouse-wheel and trackpad
  scrolling remain available when applications extend below the window.
- Add and Edit now use one Category dropdown with standard desktop categories
  such as Games, Internet and Multimedia. The same selection organizes the app
  in TuxShelf and its KDE Plasma application-menu launcher. TuxShelf's category
  filters and searches use that selection even when menu integration is disabled.
- Existing desktop-menu category choices are reused. Older standard library
  categories are recognized, and custom library categories are preserved until
  you choose a replacement. Automatic returns to the application's own metadata.
- Category choices are preserved across restarts, metadata refreshes and library
  export/import. Existing launcher identities are retained.

## Bug fixes

- Removed the duplicate library-only category field whose editable dropdown did
  not work correctly. Choosing a category now keeps the library and launcher
  category together.
- Failed download connections no longer leave temporary file handles open,
  preventing them from accumulating after repeated retries.

## Known issues

- Terminal selection and whether a terminal stays open after the app exits depend
  on the installed terminal and desktop settings. TuxShelf may not receive the
  application's output or exit status when a terminal hands it to an existing process.
- Update pause/skip preferences are local and are not included in library exports.
- The category dropdown uses standard desktop categories; custom or renamed
  Plasma application-menu sections are not detected automatically.
- Apps without recognizable category metadata appear under Other in TuxShelf
  when Automatic is selected.

## Installation/upgrade instructions

- Use TuxShelf 0.6.0 to import library exports containing the new launch options;
  older versions may reject those fields. Existing exports can still be imported.
- Exit any running TuxShelf instance using Exit TuxShelf in the tray before
  launching TuxShelf-0.6.0-x86_64.AppImage.
- Your existing library and preferences are preserved; no database migration is
  required. If an older record has different library and desktop-menu categories,
  its explicit desktop-menu choice takes precedence in TuxShelf.
