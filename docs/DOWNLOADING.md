# Downloading and adding applications

Click **Add Application**, then choose **Add a local file…** or **Download from a
link…**. Dropping an existing AppImage onto TuxShelf still opens the local Add form
directly.

## Download from a repository

1. Paste a repository or release link and click **Find releases**. GitHub,
   GitLab.com, Codeberg and the self-hosted Forgejo/Gitea/GitLab sources used by
   update checks are supported. GitHub `owner/repo` shorthand also works.
2. Select a release file from the table. TuxShelf lists AppImages and possible raw
   Linux executables for your CPU architecture from the provider's recent releases.
   Archives, packages, metadata and clearly incompatible platforms are excluded.
   Unknown-architecture filenames remain candidates and are validated after download.
3. Enable **Include pre-releases / nightly builds** to include those releases.
   Drafts are never listed. Selecting a nightly also enables future pre-release
   checks for that app when you finish adding it.
4. Choose a download folder and click **Download and continue**. The folder list
   shares the folders configured in **Discover applications**, including its defaults
   when you have not configured them. Only existing writable, non-symlink folders
   are offered. **Add folder…** lets you choose/create another folder in the folder
   picker and saves it for discovery too. If none are available, the dialog asks you
   to add one before you can download.
5. When the download finishes, review the usual Add form: name, icon, update source,
   category, desktop-menu integration and launch options. Click **Add to library**.
   The update source is prefilled, and the selected asset variant and release version
   are retained for future checks. If you change the source, the old source's asset
   pattern and nightly preference are not applied to the replacement source.

The destination uses the release asset's filename. Existing files, directories and
symlinks are never overwritten, even if another process creates a file while the
transfer is running. If a regular file with the selected name already exists,
TuxShelf checks its size, format and any available published checksum, then
continues to the Add form using that file without downloading it again. This
works across restarts and requires no manual file selection. Invalid or mismatched
files are reported and left untouched; directories and symlinks cannot be reused.
New downloads are made executable; reusing an existing file preserves its permissions.
Downloading and inspecting an app never runs it.

## Validation and cancellation

Downloads use HTTPS and the existing update download/validation pipeline. TuxShelf
checks the published size when available, validates the application format and
verifies a published SHA-256/SHA-512 digest or supported checksum file when present.
The final Add form reports the checksum result. Missing checksums do not prevent a
valid download; publisher signatures are not verified.

Cancel stops an in-progress transfer and removes its temporary file. A current
network request may take until its timeout to finish. Closing the download dialog
waits for the worker's completion without blocking the interface. A completed file
is kept if you close during completion or cancel the final Add form; no library
entry is created until you approve that form. Retrying **Download and continue**
automatically checks and uses the saved file, including downloads from earlier
sessions. When no published checksum is available, the Add form reports that;
filename and format checks alone cannot prove a file matches the selected release.
A file changed after checking is rejected by the final Add form.

This flow uses supported repository release APIs; it does not scrape arbitrary
websites or unpack `.zip`, `.tar.gz`, `.deb` or `.rpm` files. A release link shows
recent releases from its repository, so select the desired release/file in the
table. Releases outside the provider's recent-release window may not appear.
Network/authentication/rate-limit errors are reported without registering an app.
