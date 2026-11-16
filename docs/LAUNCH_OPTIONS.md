# Advanced launch options

## Launch profiles

The **Launch** button has a small arrow on its right. Open it to choose **Default**
or a named profile, then click **Launch**. The checked menu item and Launch tooltip
identify the selected profile. Selection is remembered while this TuxShelf window
is open, including card refreshes; a new session starts with Default. Choosing a
profile does not launch the app until you click Launch (or double-click its card
outside selection mode).

Choose **Edit profiles…** in this dropdown to manage profiles. The same editor is
available as **Edit launch profiles…** in the card's three-dot menu, including for
missing files. **Default** is always present and uses the existing environment
variables and launch options from Add/Edit. Editing Default here updates those
same settings and any managed desktop-menu launcher.

**New profile** copies Default's current settings. Give it a unique name such as
Debug, then edit its environment variables, arguments, working directory or terminal
setting. Profiles are independent: clearing a field removes that preference for
that profile rather than inheriting it from Default. Later changes to Default do
not alter existing named profiles. The application still inherits TuxShelf's cleaned
process environment, with the selected profile's variables applied on top.

Rename a profile in its **Name** field, or choose **Delete profile** to remove it.
Default cannot be renamed or deleted. **Save profiles** saves all edits together;
**Cancel** discards all edits, including newly created or deleted profiles. Up to
32 additional profiles are supported, with unique names of up to 64 characters.

Tray, application-details and desktop-menu launches continue to use Default.
Named profiles use the same executable and update source as Default; they only
change launch settings. Profile selection does not affect other apps.

## Editing Default from Add/Edit

In **Add application** or **Edit information…**, click **Launch options…** beside
the environment-variable heading. Choose **Use options**, then save the parent
Add/Edit dialog. Canceling the parent dialog discards these changes. **Reset to
defaults** clears arguments, the custom folder and terminal mode when saved.

## Command-line arguments

Enter arguments without repeating the executable's path. For example:

```text
--profile "Work profile" --verbose
```

Values containing spaces can be enclosed in single or double quotes. An empty
quoted value (`""`) passes an empty argument. Quotes must be balanced. Arguments
are passed directly to the executable: shell commands, pipes, redirects, `$HOME`,
command substitutions and wildcards are not expanded or executed. To pass a
literal backslash, quote or escape it as in shell-style argument syntax.

Default's arguments are used when launching from TuxShelf with Default, its tray,
or a managed desktop-menu launcher. Existing application file/URL markers in desktop launchers
are kept after the configured arguments; a literal `%U` typed here stays literal.
Up to 8,192 characters and 256 arguments are supported.

## Working directory

Use **Browse…** to select a directory, or enter an absolute path. A leading `~/`
is expanded to your home directory when saved. Leave it blank to use the folder
containing the application, which is the existing default and follows the file
when it is relocated.

A custom folder is remembered independently of the executable's location. Missing
folders can be saved for later reconnection or transfer, but TuxShelf refuses to
launch until the folder exists or you clear/change it. Desktop launchers receive
the same folder in their `Path` setting; missing-folder behavior depends on the
desktop launcher.

## Run in terminal

Enable this for interactive scripts or command-line tools. TuxShelf first looks
for `xdg-terminal-exec`, then tries installed terminal emulators. On KDE, Konsole
is preferred among the fallbacks. Other supported fallbacks are GNOME Terminal,
Xfce Terminal, kitty, Alacritty, foot and xterm. If none is found, TuxShelf shows
an error and you can disable terminal mode or install a supported terminal.

Desktop-menu launchers use the standard `Terminal=true` property, so the desktop
chooses the terminal. Both routes use the same application arguments, working
directory and environment preferences. Launches remain detached from TuxShelf.
The terminal's own settings determine whether it stays open after the app exits.
Interactive input/output appears in the terminal; TuxShelf's launch log captures
the terminal process output, which may not include the child application's output
or final exit status when the terminal hands work to an existing process.

## Persistence and library transfers

Launch options live in existing application metadata. They survive restarts,
metadata refreshes, updates and rollback without a database migration. Managed
desktop launchers keep their existing identity when options change.

Library exports include named profiles as well as Default's preferences, and
imports validate and restore them. Environment variables for all profiles follow
the existing opt-in export/import environment checkboxes; they are excluded by
default. Other profile preferences are included normally.
Paths remain absolute and may need changing on another machine. Arguments are
plain text in the exported JSON, so avoid putting secrets in them. Importing or
editing preferences does not execute an application. Older TuxShelf builds may
reject exports containing these new launch-option fields.
