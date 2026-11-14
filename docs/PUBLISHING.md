# Publishing AppForge from the local checkout

Run these commands in a Linux terminal from `/home/thilen/appforge/`.
Python 3.10+ and Git are required; releases additionally require authenticated `gh`.
The ChatGPT source-folder sandbox may allow source edits while protecting `.git`;
that is why publishing is performed from the user's terminal.

```bash
./scripts/publish.sh push --dry-run
./scripts/publish.sh push
./scripts/publish.sh release --dry-run
./scripts/publish.sh release
```

A dry run is offline and read-only. It does not stage, fetch, commit, push or call
GitHub. Release preview still requires valid local build/test evidence. It cannot
confirm remote availability or the absence of an existing release/tag.

The public roots are `.gitignore`, `src/`, `docs/`, `packaging/`, `scripts/`,
`tests/`, public `releases/RELEASE_NOTES_v<version>.md` files, `README.md`,
`pyproject.toml`, and the three explicit requirements files. Other release-folder
files and private/internal notes remain excluded.
Nested secrets, private instructions, caches, symlinks and generated files are
excluded by an independent policy as well as `.gitignore`. Known token/private-key
patterns cause a stop without printing their contents. This is a heuristic, not a
complete secret detector: inspect the full proposed diff before approving.

`push` fetches the configured main branch without tags and stops if its tip changed,
is ahead, or diverged. It never pulls, merges, rebases, forces, or rewrites history.
It checks outgoing commits as well as the new snapshot. Excluded tracked paths,
are removed from the index with
`git rm --cached`; local files remain untouched and previous commits retain them.
Conflicting staged changes cause a stop rather than a forced removal.

The script prints the staged diff and existing outgoing commits before requiring
`PUSH`. Staging occurs before this confirmation; cancellation leaves staged changes
available for review. A descriptive commit-message prompt follows. No empty commit
is made. A rejected push leaves any new local commit intact; resolve it manually.
Network/authentication errors stop the command and are reported.

## Prepare a release

Ask Codex to "Prepare release", optionally specifying the desired version. Codex
will inspect the current version, previous release notes/tags and verified changes.
If no version was specified, it will propose one and wait for your confirmation.
It updates relevant version declarations, public README/docs and tests as needed,
and creates `releases/RELEASE_NOTES_v<version>.md` with the heading
`# AppForge <version>`. Dates are included only when confirmed. Notes describe
verified user-visible changes and omit empty sections; historical notes remain
intact. Preparation never builds or modifies AppImages or publishes anything.

Codex reports the previous/new versions, files changed, documented features/fixes,
notes location, automated test results and remaining build/manual-testing work.
Automated tests are not a claim that you manually tested the AppImage.

## Release evidence and approval

`release` first selects the highest-version AppImage and checks its matching public
notes. It prints the notes and requires you to type `TESTED <version> <sha256>` to
confirm you personally tested and approve that exact binary. This terminal prompt
is distinct from automated test evidence; a dry run never assumes approval.
The script then runs the approved source push. It can publish source successfully
and then stop on a provenance or later release check. To avoid a stale build, push the source, build and
test that exact committed version, then run `release` with no further source edits.
The second source workflow still asks for confirmation, even if no new commit is
needed. Existing release files are never deleted or overwritten by the publisher.

The selected asset is the highest SemVer file matching
`dist/AppForge-<version>-x86_64.AppImage`. Numeric version ordering is used;
prereleases sort below their stable version. Build metadata does not affect order;
equal-precedence candidates stop as ambiguous. Unversioned and other-architecture
files are not selected. Both project version declarations must match the asset.

A controlled build/test process must produce a sidecar named
`<asset>.provenance.json` beside the AppImage, for example
`dist/AppForge-0.5.5-x86_64.AppImage.provenance.json`, with this schema:

```json
{
  "schema": 1,
  "asset": "AppForge-0.5.5-x86_64.AppImage",
  "version": "0.5.5",
  "source_commit": "<full 40-character Git commit ID>",
  "source_tree": "<git rev-parse HEAD^{tree}>",
  "sha256": "<SHA-256 of the built AppImage>",
  "tests": {
    "passed": true,
    "exit_code": 0,
    "log": "tests.log",
    "sha256": "<SHA-256 of tests.log>"
  },
  "appimage_selftest": {
    "passed": true,
    "exit_code": 0,
    "log": "appimage-selftest.log",
    "sha256": "<SHA-256 of appimage-selftest.log>"
  }
}
```

Logs must be nonempty, regular files inside `dist/`, addressed by relative paths,
and their hashes must match. The build must use the exact recorded committed
source without local public changes. `tests` represents successful relevant tests;
`appimage_selftest` represents testing the actual built AppImage, not merely running
Python source. Record actual command exit codes and output from the build/test
process. Do not hand-create a passing record for an old, unverified binary.

This publisher verifies local evidence consistency; it is not a signed CI
attestation verifier and cannot establish the honesty of an arbitrarily fabricated
record. It intentionally does not manufacture evidence, run tests, or rebuild
assets during publication. Existing builds without evidence stop safely and need
a controlled rebuild/test step before they can be released.

After evidence checks, the script authenticates `gh` and checks remote releases
and tags. An existing release stops the workflow; an existing tag must already
identify the verified source commit. A missing tag is created by GitHub at that
exact commit during release creation. A separate `RELEASE` confirmation is required.
Only the selected AppImage is uploaded as an asset; no logs, archives, provenance
files or other assets are uploaded. The exact matching public notes file is passed
with `--notes-file` as the GitHub Release description. Other versions' notes and
private/internal files are never combined into that description. The notes must
be nonempty, carry the matching version heading and remain unchanged throughout
approval, source push and release creation. The final RELEASE confirmation
approves publication of these notes and the binary. The release body and asset
are verified after creation.

The script never uses `--clobber` and never moves a tag. Changing an existing
release or tag requires separate explicit approval and manual review. GitHub
release creation can partially succeed before an upload/network error; inspect
the reported remote state manually rather than deleting or overwriting it.
