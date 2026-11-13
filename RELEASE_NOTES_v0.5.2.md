# Patch notes – v0.5.2

## New features
- **Application menu category.** *Add application* and *Edit application* now have an
  **Application menu category** dropdown. It lists the KDE/freedesktop main sections (Development, Education,
  Games, Graphics, Internet, Multimedia, Office, Science & Math, Settings, System, Utilities) plus
  **Automatic (from the application)**. The choice is written to the launcher's `Categories=` line, so the
  app is filed under that section in the KDE application launcher.
  - The chosen category is placed first; the app's own *main* categories are dropped so it isn't listed in
    several sections, while additional ones (e.g. `Qt`, `Emulator`) are kept.
  - *Automatic* keeps the previous behaviour.
- **Environment variables.** *Add application* and *Edit application* now have an **Environment variables**
  field (one `NAME=value` per line; blank lines and `#` comments are ignored; an optional `export ` prefix is
  accepted).
  - In the `.desktop` file they are written as `Exec=env NAME=value … /path/to/app`, the same way KDE's menu
    editor does it.
  - When you press **Launch** in AppForge, the same variables are applied to the started process. They are
    applied after AppForge's own environment clean-up, so they always win.
  - Invalid lines are reported inline and block *Add to library* / *Save changes* until fixed.

## Modified functionality
- `LibraryService.add_application()` accepts `menu_category` and `env_vars`;
  `LibraryService.update_application()` accepts `menu_category` and `env_vars` (omitting them leaves the stored
  values unchanged; `None`/empty clears them). Both are validated and raise `LibraryError` on bad input.
- Saving in *Edit* rewrites the launcher of apps that are in the application menu, so the new category and
  variables take effect immediately. For apps that aren't in the menu the values are stored and used the
  next time the launcher is created (and for *Launch* straight away).
- The Add dialog is taller (560×770) and the Edit dialog grows to fit the new fields.

## Technical changes
- New module `core/envvars.py` (Qt-free): parsing, validation and storage helpers. Variables are stored in
  `entry.metadata["env_vars"]`; the category in `entry.metadata["menu_category"]` (no database migration needed).
- `core/desktop/service.py`: `MENU_CATEGORIES`, `menu_category_of()`, category merging and the `env` prefix in
  `render_entry()`; arguments are quoted with the existing spec-conformant Exec quoting.
- `services/launcher.py`: `launch()` merges the app's variables into the child environment.
- Version bumped 0.5.1 → 0.5.2 (`pyproject.toml`, `appforge/__init__.py`, README).
- README documents both options.
- New tests in `tests/test_menu_env.py` (13 cases, including a real launch that checks the variable reaches
  the process); the full suite passes (160 tests).

## Notes
- Existing apps are unaffected until you set a category or variables.
- Variables are not shell-expanded; `$HOME` in a value is passed literally.
