# AppForge 0.5.4

## Modified functionality
- **Settings button is now a gear.** It is an icon-only button in the bottom-right corner of the window
  (the status bar's right-hand slot) instead of a text button between *Update All* and *Add Application*.
  The gear is drawn in the theme's accent colour, the same blue as the primary buttons, and is re-tinted
  when the system switches between light and dark. Tooltip: "Settings".
- **Update sources accept more sites.** Besides GitHub, GitLab.com and Codeberg, any `https://` repository
  URL on another host is accepted, e.g. `https://git.magicbean.dev/MagicBeanDev/Longshot`. Accepted forms:
  `https://host/owner/repo`, `host/owner/repo(.git)`, `git@host:owner/repo.git`, release/`src` page URLs
  (trimmed to the repository), `host:port`, and nested `group/sub/project` paths.
  - For such hosts AppForge asks the Forgejo/Gitea release API first and then GitLab's, and remembers which
    one answered. Network and rate-limit errors are reported straight away (no second probe).
  - Safety is unchanged or stricter: unknown hosts must use `https://` (plain `http://` and URLs with
    embedded credentials are rejected), the GitHub token is never sent to them, and only `https://`
    asset links are used.
  - Hint texts and placeholders in *Add application* / *Edit* and the "no update source" messages no longer
    say "GitHub only".

## Bug fixes
- **Black box on drop-down lists** (category, status, sort and other combo boxes). The popup was made
  translucent, which rendered as a black box on some systems. The list is now an ordinary opaque window
  clipped to rounded corners with a mask, and the arrow is drawn by the widget itself instead of by the
  style's drop-down sub-control (stylesheet: `::drop-down` and `::down-arrow` neutralised, extra right padding).
  Context menus are unchanged.

## Technical changes
- `core/updates/providers.py`: new `custom` provider, `SourceRef.host` field, `SelfHostedClient`;
  `ForgejoClient`/`GitLabClient` accept a label for error messages.
- `ui/icons.py`: `gear_pixmap` / `gear_icon` (vector-drawn, 1x/2x/3x).
- `ui/popups.py`: `round_combo_popup`, `RoundedComboBox.paintEvent` (chevron).
- Version bumped to 0.5.4 (`__init__.py`, `pyproject.toml`, README).
- Tests: updated parser/popup tests; added tests for self-hosted parsing and probing, and for the gear button.

## Not verified
- The test environment used to prepare this update had no Qt, so the GUI changes (gear, combo-box popup and
  arrow) and the GUI tests have not been run or looked at; the provider logic was exercised with fake servers.
  Please check the drop-downs and the gear on your system, and tell me if the black box persists.
- No AppImage was built for this update.
