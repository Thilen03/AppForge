# AppForge 0.6.1

## New features

- **Add Application** now offers a local-file option and **Download from a link…**.
  Paste a GitHub, GitLab, Codeberg or supported self-hosted repository/release link,
  select an AppImage or raw Linux executable, and choose a download folder.
- Download folders are shared with **Discover applications**. Add another folder
  from the download dialog when needed. Only writable, existing folders are offered.
- Downloads show progress, support cancellation, validate the application and verify
  published checksums when available. Existing destination files are never overwritten.
- After downloading, review the usual Add form with the update source prefilled.
  Adding the app retains the selected release version, asset variant and nightly
  preference for future updates. Cancelling the form keeps the downloaded file.

## Improvements

- Enable pre-release/nightly updates directly from an app's card menu. Choose
  **Use stable releases only** to switch back. The preference is saved per app.
- The README is shorter, with detailed everyday guidance moved to a dedicated
  usage guide and links to the other feature guides.
- Update checks can use a version from the release title or selected filename when
  the repository uses an unnumbered tag such as `continuous`.
- When versions cannot be compared, AppForge can compare the installed file with
  the selected release file's published SHA-256 or SHA-512 checksum. Matching files
  show as up to date. Different files can be installed after a warning that their
  version order is unknown. The same check can detect rolling release rebuilds
  that keep their filename version.
- Update status messages explain when to edit the installed version or choose a
  release file. Unexpected check errors report a failure instead of leaving the
  application stuck checking.

## Bug fixes

- Choosing an asset while a card says **Pre-releases available** now offers to
  enable pre-releases for that app and rechecks the selected file. Previously the
  file choice left pre-releases excluded, so no Update button appeared. Downloads
  still begin only when you choose Update for an eligible release.
- Improved detection of dates, underscore-separated versions, numbered builds and
  versions in filenames whose application names also contain digits.
- Choosing a versioned file from an unnumbered release now creates a reusable file
  pattern, so the choice can follow later releases.
- Saved file patterns no longer silently fall back to a different release variant.
- Architecture filtering recognizes compound names such as `x86_64` and `x86-64`,
  including when choosing files manually. Archives named after an AppImage are
  excluded from AppImage choices.
- Invalid published asset checksums are rejected. Unnamed hashes in shared checksum
  lists are not assumed to belong to the selected application.

## Known issues

- If neither usable version information nor a published checksum exists, AppForge
  cannot determine whether the installed file needs updating. Set its installed
  version in Edit when known.
- Different checksums establish that files differ, not which one is newer. Review
  the release before accepting an update offered through checksum comparison.

## Installation/upgrade instructions

Once this release is published, use AppForge's self-update or download
`AppForge-0.6.1-x86_64.AppImage`, make it executable and launch it. Existing library
settings and registered applications are retained; no database migration is required.

Repository downloads and updates require an AppImage or raw Linux executable.
Archives and packages such as `.zip`, `.tar.gz`, `.deb` and `.rpm` are not unpacked.
