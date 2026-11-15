# AppForge 0.6.4

## Improvements

- Search scanned applications by name, filename/location, version, format, status
  or update source. Results filter as you type and show a matching count.
- Click discovery result headings to sort, including A–Z/Z–A application names.
  Checkmarks and source edits stay with the correct app. Bulk selection, import
  and ignore actions apply to visible search matches.

## Bug fixes

- Discovery filters for AppImages and common Linux executable filenames before
  inspecting contents, avoiding unnecessary reads of ROMs and other unrelated
  files, including files incorrectly marked executable. Extensionless and
  versioned executables remain supported. Files still need valid AppImage, ELF
  or shebang-script contents to appear in results.
- **Download and continue** now checks and uses an existing file with the selected
  name automatically, including after cancelling the Add form or restarting
  AppForge. Size, format and available published checksums are checked before
  reopening the Add form. Existing files are never overwritten.

## Installation/upgrade instructions

Once published, use AppForge's self-update or download
`AppForge-0.6.4-x86_64.AppImage`, make it executable and launch it. Existing
applications and preferences are retained; no database migration is required.
Discovery still scans all saved folders; folder checkboxes control background
watching only. Supported executables with unusual filename extensions can still
be added through **Add Application → Add a local file… → All files**.
