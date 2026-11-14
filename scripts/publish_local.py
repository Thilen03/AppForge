#!/usr/bin/env python3
"""Reviewed local publishing; dry runs never write the index or contact GitHub."""
from __future__ import annotations

import argparse
import fnmatch
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = 'Thilen03/AppForge'
URLS = {f'https://github.com/{REPO}.git', f'git@github.com:{REPO}.git'}
DIRECTORIES = {'src', 'docs', 'packaging', 'scripts', 'tests', 'releases'}
FILES = {'.gitignore', 'README.md', 'pyproject.toml', 'requirements.txt',
         'requirements-dev.txt', 'requirements-build.txt'}
PRIVATE = {'.git', '.agents', '.codex', '.aws', '.ssh', '.gnupg', '.idea', '.vscode',
           '.venv', 'venv', 'env', 'build', 'dist', 'node_modules', '__pycache__',
           '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox', '.nox', '.cache',
           'htmlcov', 'secrets', 'credentials', 'AGENTS.md',
           'development-instructions.md', 'roadmap.md'}
PATTERNS = ('.env*', '*.env', '.venv-*', '*.py[cod]', '*.egg-info',
            '*.pem', '*.key', '*.p12', '*.pfx', '*.keystore', '*credentials*.json',
            'credentials.*', 'secrets.*', '*.AppImage', '*.so', '*.o', '*.zip',
            '*.tar', '*.tar.*', '*.sqlite*', '*.db', '*.bak', '*.tmp', '*.temp',
            '*.log', '*~', '*.swp', '*.swo', '.coverage*', 'coverage.xml',
            'RELEASE_NOTES*.md', '.DS_Store')
# A heuristic backstop; final human review is still required. Never print matches.
SECRET = re.compile(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
                    rb'github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|'
                    rb'AKIA[0-9A-Z]{16}')
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                    r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')


class Stop(RuntimeError):
    pass


def allowed(name):
    parts = Path(name).parts
    if not parts or any(part in PRIVATE for part in parts):
        return False
    if parts[0] == 'releases':
        if len(parts) != 2:
            return False
        match = re.fullmatch(r'RELEASE_NOTES_v(.+)\.md', parts[1])
        if not match:
            return False
        try:
            semver(match[1])
        except Stop:
            return False
        return True
    return (parts[0] in DIRECTORIES or name in FILES) and not any(
        any(fnmatch.fnmatchcase(part, pat) for pat in PATTERNS) for part in parts)



def semver(text):
    match = SEMVER.fullmatch(text)
    if not match:
        raise Stop(f'Invalid semantic version: {text}')
    pre = match[4].split('.') if match[4] else []
    if any(p.isdigit() and len(p) > 1 and p.startswith('0') for p in pre):
        raise Stop(f'Invalid prerelease version: {text}')
    return tuple(map(int, match.group(1, 2, 3))), pre


def compare_versions(a, b):
    ac, ap = semver(a)
    bc, bp = semver(b)
    if ac != bc:
        return (ac > bc) - (ac < bc)
    if not ap or not bp:
        return (not ap) - (not bp)
    for x, y in zip(ap, bp):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return (int(x) > int(y)) - (int(x) < int(y))
        if x.isdigit() != y.isdigit():
            return -1 if x.isdigit() else 1
        return (x > y) - (x < y)
    return (len(ap) > len(bp)) - (len(ap) < len(bp))


def sha256(path):
    with path.open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
        return h.hexdigest()


class Publisher:
    def __init__(self, root, dry_run=False):
        self.root = Path(root).resolve()
        self.dry_run = dry_run
        self.remote_tip = None
        self.env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
                        GH_PROMPT_DISABLED='1', GH_HOST='github.com', GIT_LITERAL_PATHSPECS='1')
        if any(k in os.environ for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                                         'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY',
                                         'GIT_ALTERNATE_OBJECT_DIRECTORIES')):
            raise Stop('Remove Git metadata/index overrides from the environment first.')

    def run(self, args, check=True, stream=False):
        output = {} if stream else {'capture_output': True}
        result = subprocess.run(args, cwd=self.root, env=self.env, **output)
        if check and result.returncode:
            raise Stop(f'Command failed ({result.returncode}): {args[0]} {args[1]}\n'
                       + (result.stderr or b'').decode(errors='replace'))
        return result

    def git(self, *args):
        return self.run(['git', *args]).stdout.decode(errors='surrogateescape').strip()

    def names(self, *args):
        return [p for p in self.run(['git', *args, '-z']).stdout.decode(
            errors='surrogateescape').split('\0') if p]

    def confirm(self, word, description):
        if not sys.stdin.isatty():
            raise Stop('Confirmation requires an interactive terminal. Nothing approved.')
        if input(f'{description}\nType {word} to continue: ').strip() != word:
            raise Stop('Cancelled. No further action taken; existing index changes remain.')

    def identity(self):
        if self.git('rev-parse', '--show-toplevel') != str(self.root):
            raise Stop('Unexpected repository root.')
        if self.git('symbolic-ref', '--short', 'HEAD') != 'main':
            raise Stop('Expected branch main; detached HEAD is not supported.')
        if self.git('rev-parse', '--abbrev-ref', '@{upstream}') != 'origin/main':
            raise Stop('Expected upstream origin/main.')
        for args in (('remote', 'get-url', '--all', 'origin'),
                     ('remote', 'get-url', '--push', '--all', 'origin')):
            if self.git(*args) not in URLS:
                raise Stop('Unexpected or multiple origin URLs.')
        gitdir = Path(self.git('rev-parse', '--absolute-git-dir'))
        for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge',
                       'rebase-apply', 'index.lock'):
            if (gitdir / marker).exists():
                raise Stop(f'Unfinished Git operation or lock: {marker}')
        if not self.dry_run and not os.access(gitdir, os.W_OK):
            raise Stop('.git is read-only. Run this script in your Linux terminal.')

    def check_remote(self):
        previous = self.git('rev-parse', 'refs/remotes/origin/main')
        self.git('fetch', '--no-tags', 'origin',
                 'refs/heads/main:refs/remotes/origin/main')
        current = self.git('rev-parse', 'refs/remotes/origin/main')
        if current != previous:
            raise Stop('Remote main changed. Review it manually; no automatic merge/rebase.')
        if self.run(['git', 'merge-base', '--is-ancestor', current, 'HEAD'], check=False).returncode:
            raise Stop('Remote main is ahead or diverged. No commit or push performed.')
        self.remote_tip = current
        # A push sends all outgoing commits, not just this invocation's snapshot.
        outgoing = self.git('rev-list', current + '..HEAD').splitlines()
        for commit in outgoing:
            for name in self.names('diff-tree', '--root', '--no-commit-id', '-r',
                                   '--no-renames', '-m', '--diff-filter=ACMT', '--name-only', commit):
                if not allowed(name):
                    raise Stop(f'Unpushed history adds excluded content: {name!r}; review manually.')
                self.check_content(name, self.run(['git', 'show', f'{commit}:{name}']).stdout)

    def plan(self):
        tracked = set(self.names('ls-files', '--cached'))
        candidates = tracked | set(self.names('ls-files', '--others', '--exclude-standard'))
        ignored = set(self.names('ls-files', '--cached', '--ignored', '--exclude-standard'))
        remove, stage = [], []
        for name in sorted(candidates):
            path = self.root / name
            safe = allowed(name) and name not in ignored
            # Never follow a symlink to private content, including ancestor directories.
            if any(p.is_symlink() for p in (path, *path.parents)):
                safe = False
            if not safe:
                if name in tracked:
                    remove.append(name)
                continue
            if path.exists() and not path.is_file():
                raise Stop(f'Unsupported tracked path (directory/submodule): {name!r}')
            if path.is_file():
                self.check_content(name, path.read_bytes())
            stage.append(name)
        return remove, stage

    @staticmethod
    def check_content(name, content):
        if SECRET.search(content):
            raise Stop(f'Possible secret in {name!r}. Review locally; content was not printed.')

    def remote_unchanged(self):
        output = self.git('ls-remote', '--exit-code', 'origin', 'refs/heads/main')
        if output.split()[0] != self.remote_tip:
            raise Stop('Remote main changed during review. Stopping without pushing.')

    def push(self):
        self.identity()
        if not self.dry_run:
            self.check_remote()
        remove, stage = self.plan()
        print('Index-only removals (local files preserved):')
        for name in remove:
            print('  untrack', repr(name))
        print('Approved paths to stage/review:')
        for name in stage:
            print('  stage', repr(name))
        if self.dry_run:
            print('DRY RUN: no fetch, staging, commit, push, or network request performed.')
            return
        for name in remove:
            self.git('rm', '--cached', '--', name)  # no force; conflicts fail safely
        for name in stage:
            self.git('add', '--', name)
        # Inspect all staged paths, including work staged before this invocation.
        changes = self.names('diff', '--cached', '--no-renames', '--diff-filter=ACMT', '--name-only')
        for name in changes:
            if not allowed(name):
                raise Stop(f'Excluded content remains staged: {name!r}')
            if self.git('ls-files', '--stage', '--', name).startswith(('120000 ', '160000 ')):
                raise Stop(f'Symlink/submodule remains staged: {name!r}')
            self.check_content(name, self.run(['git', 'show', ':' + name]).stdout)
        self.git('diff', '--cached', '--check')
        print(self.git('status', '--short', '--branch'))
        print(self.git('--no-pager', 'diff', '--cached', '--no-ext-diff', '--no-textconv'))
        outgoing = self.git('log', '--oneline', self.remote_tip + '..HEAD')
        if outgoing:
            print('Existing commits that will also be pushed:\n' + outgoing)
        snapshot = self.git('write-tree')
        head = self.git('rev-parse', 'HEAD')
        self.confirm('PUSH', 'Approve the complete staged diff and outgoing commits for commit/push?')
        self.remote_unchanged()
        if self.git('write-tree') != snapshot or self.git('rev-parse', 'HEAD') != head:
            raise Stop('Index or HEAD changed during review. Review again.')
        difference = self.run(['git', 'diff', '--cached', '--quiet'], check=False).returncode
        if difference not in (0, 1):
            raise Stop('Could not inspect staged changes. No commit performed.')
        if difference == 1:
            message = input('Commit message [Update AppForge public source and publishing workflow]: ').strip()
            self.git('commit', '-m', message or 'Update AppForge public source and publishing workflow')
        if self.git('rev-parse', 'HEAD^{tree}') != snapshot:
            raise Stop('Committed tree differs from the reviewed index (possibly a hook). No push.')
        self.remote_unchanged()
        self.git('-c', 'push.followTags=false', 'push', '--no-force', '--no-follow-tags',
                 'origin', 'HEAD:refs/heads/main')
        # Release checks must compare against the commit just pushed, not its parent.
        self.remote_tip = self.git('rev-parse', 'HEAD')
        print('Source push succeeded.')

    def select_release(self):
        if (self.root / 'dist').is_symlink():
            raise Stop('dist/ must not be a symlink.')
        matches = []
        for path in (self.root / 'dist').glob('AppForge-*-x86_64.AppImage'):
            if path.is_symlink() or not path.is_file():
                continue
            version = path.name[len('AppForge-'):-len('-x86_64.AppImage')]
            try:
                semver(version)
            except Stop:
                continue
            matches.append((version, path))
        if not matches:
            raise Stop('No semantic-version x86_64 AppImage found in dist/.')
        matches.sort(key=functools.cmp_to_key(lambda a, b: compare_versions(a[0], b[0])))
        version, asset = matches[-1]
        if len(matches) > 1 and compare_versions(matches[-2][0], version) == 0:
            raise Stop('Multiple highest-version AppImages have equal SemVer precedence.')
        if not asset.stat().st_size:
            raise Stop('Selected AppImage is empty.')
        config = (self.root / 'pyproject.toml').read_text()
        # Python 3.10 compatible: this project keeps its version in [project].
        section = re.search(r'(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)', config)
        project = re.search(r'^version\s*=\s*"([^"]+)"\s*$', section[1], re.M) if section else None
        init = re.search(r'^__version__\s*=\s*"([^"]+)"',
                         (self.root / 'src/appforge/__init__.py').read_text(), re.M)
        if not project or not init or project[1] != version or init[1] != version:
            raise Stop('Selected AppImage does not match both project version declarations.')
        return version, asset

    def provenance(self, version, asset):
        record = Path(str(asset) + '.provenance.json')
        try:
            if record.is_symlink():
                raise Stop('Provenance must not be a symlink.')
            data = json.loads(record.read_text())
            if data['schema'] != 1 or data['version'] != version or data['asset'] != asset.name:
                raise Stop('Provenance version/asset/schema mismatch.')
            if data['sha256'] != sha256(asset):
                raise Stop('AppImage hash does not match build provenance.')
            commit = data['source_commit']
            if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
                raise Stop('Provenance must identify a full source commit.')
            if commit != self.git('rev-parse', 'HEAD'):
                raise Stop('AppImage was not built from current HEAD. Build/test after the source push.')
            if data['source_tree'] != self.git('rev-parse', 'HEAD^{tree}'):
                raise Stop('Build source tree mismatch.')
            if self.git('diff', '--no-ext-diff', '--no-textconv', 'HEAD', '--',
                        *sorted(DIRECTORIES | FILES)):
                raise Stop('Public source changed after the recorded build.')
            if self.names('ls-files', '--others', '--exclude-standard'):
                raise Stop('Untracked public files prevent provenance verification.')
            for key in ('tests', 'appimage_selftest'):
                evidence = data[key]
                if evidence['exit_code'] != 0 or evidence['passed'] is not True:
                    raise Stop(f'Missing passing {key} evidence.')
                log = Path(evidence['log'])
                if log.is_absolute() or '..' in log.parts:
                    raise Stop('Evidence logs must be relative paths inside dist/.')
                path = self.root / 'dist' / log
                if any(p.is_symlink() for p in (path, *path.parents)):
                    raise Stop('Evidence logs cannot use symlinks.')
                if not path.is_file() or not path.stat().st_size or sha256(path) != evidence['sha256']:
                    raise Stop(f'Missing or changed {key} log.')
            return commit, sha256(asset)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Stop('Cannot confirm build provenance/tested status. A verified build record '
                       f'and logs are required: {record.name}') from exc

    def remote_release(self, tag):
        # List operations distinguish absence from authentication/network failures.
        refs = self.git('ls-remote', 'origin', 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}')
        result = self.run(['gh', 'api', '--paginate', '--slurp',
                           f'repos/{REPO}/releases?per_page=100'])
        pages = json.loads(result.stdout)
        if any(item['tag_name'] == tag for page in pages for item in page):
            raise Stop('Release already exists. No overwrite; review it manually.')
        if refs:
            lines = [line.split() for line in refs.splitlines()]
            peeled = next((sha for sha, ref in lines if ref.endswith('^{}')), lines[0][0])
            if peeled != self.git('rev-parse', 'HEAD'):
                raise Stop('Existing release tag points elsewhere. It will not be moved.')
        return bool(refs)

    def release_notes(self, version):
        path = self.root / 'releases' / f'RELEASE_NOTES_v{version}.md'
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise Stop('Matching release notes must not use symlinks.')
        if not path.is_file() or not path.stat().st_size:
            raise Stop(f'Matching public release notes are missing or empty: {path.name}')
        text = path.read_text(encoding='utf-8')
        heading = re.search(r'^# AppForge v?([^\s]+)[ \t]*$', text, re.M)
        if not heading or heading[1] != version:
            raise Stop('Release-notes version heading does not match the AppImage.')
        if not text[heading.end():].strip():
            raise Stop('Release notes contain no user-facing changes.')
        self.check_content(str(path.relative_to(self.root)), path.read_bytes())
        return path, sha256(path)

    def optional_provenance(self, version, asset):
        """Validate supplied evidence; manual user approval handles ordinary builds."""
        record = Path(str(asset) + '.provenance.json')
        if record.exists() or record.is_symlink():
            return self.provenance(version, asset)
        return None

    def release_source(self):
        if self.git('diff', '--no-ext-diff', '--no-textconv', 'HEAD', '--',
                    *sorted(DIRECTORIES | FILES)):
            raise Stop('Public source changed during publishing. Run push and review again.')
        if any(allowed(name) for name in self.names('ls-files', '--others', '--exclude-standard')):
            raise Stop('New public files appeared during publishing. Run push and review again.')
        return self.git('rev-parse', 'HEAD')

    def release(self):
        version, asset = self.select_release()
        notes, notes_digest = self.release_notes(version)
        digest = sha256(asset)
        evidence = self.optional_provenance(version, asset)
        print(f'Selected AppImage: {asset.name} ({asset.stat().st_size} bytes)', flush=True)
        print(f'SHA-256: {digest}')
        print(f'Public release notes: {notes.relative_to(self.root)}')
        if evidence is None:
            print('Manual build: you will confirm that you built and tested this exact AppImage.')
        else:
            print('Automated build/test record verified; your manual testing approval is still required.')
        if self.dry_run:
            self.push()
            print(notes.read_text(encoding='utf-8'))
            print('DRY RUN: local release checks passed. No publishing or testing approval assumed.')
            print('GitHub authentication, remote release/tag availability and source push are not checked offline.')
            return
        # Fail on authentication/existing release/tag conflicts before asking approval.
        self.identity()
        print('Checking GitHub authentication and release availability...', flush=True)
        self.run(['gh', 'auth', 'status'])
        self.remote_release('v' + version)
        # Keep the working source-push workflow and its own explicit approval.
        print('Reviewing and publishing approved source changes first...', flush=True)
        self.push()
        commit = self.release_source()
        if self.select_release() != (version, asset) or sha256(asset) != digest:
            raise Stop('AppImage changed during source publication. Review/test the selected binary again.')
        if self.release_notes(version) != (notes, notes_digest):
            raise Stop('Release notes changed during source publication. Review again.')
        if self.optional_provenance(version, asset) != evidence:
            raise Stop('Build/test evidence changed during source publication. Review again.')
        existing_tag = self.remote_release('v' + version)
        print(f'Ready to publish AppForge {version} at source commit {commit}')
        print(f'Asset: {asset.name}; SHA-256: {digest}')
        print(notes.read_text(encoding='utf-8'))
        self.confirm('RELEASE',
                     'Confirm you built this AppImage from the prepared release source, personally '
                     'tested this exact file, and approve publishing it with these notes.')
        self.remote_unchanged()
        if (self.release_source() != commit or self.select_release() != (version, asset)
                or sha256(asset) != digest or self.optional_provenance(version, asset) != evidence
                or self.release_notes(version) != (notes, notes_digest)):
            raise Stop('Release inputs changed during review. Approval is invalid; nothing uploaded.')
        existing_tag = self.remote_release('v' + version)
        args = ['gh', 'release', 'create', 'v' + version, str(asset), '--repo', REPO,
                '--title', 'AppForge ' + version, '--notes-file', str(notes)]
        args += ['--verify-tag'] if existing_tag else ['--target', commit]
        if semver(version)[1]:
            args.append('--prerelease')
        print(f'Uploading {asset.name} to GitHub Release v{version}...', flush=True)
        self.run(args, stream=True)
        print('Upload command completed; verifying the GitHub release...', flush=True)
        result = self.run(['gh', 'release', 'view', 'v' + version, '--repo', REPO,
                           '--json', 'url,assets,tagName,body'])
        data = json.loads(result.stdout)
        if data['body'].replace('\r\n', '\n').strip() != notes.read_text(encoding='utf-8').replace('\r\n', '\n').strip():
            raise Stop('Release created but published release description verification failed.')
        assets = data['assets']
        if data['tagName'] != 'v' + version or len(assets) != 1 or assets[0]['name'] != asset.name or assets[0]['size'] != asset.stat().st_size:
            raise Stop('Release created but asset verification failed. Inspect GitHub manually.')
        remote_digest = assets[0].get('digest')
        if remote_digest and remote_digest != 'sha256:' + digest:
            raise Stop('Release created but uploaded asset digest verification failed.')
        if sha256(asset) != digest:
            raise Stop('Local asset changed during upload. Inspect the release manually.')
        print('Release verified: ' + data['url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['push', 'release'])
    parser.add_argument('--dry-run', action='store_true', help='Offline read-only preview; no staging or network')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if root != Path('/home/thilen/appforge'):
        raise Stop('Run the installed script from /home/thilen/appforge/ only.')
    publisher = Publisher(root, args.dry_run)
    getattr(publisher, args.command)()


if __name__ == '__main__':
    try:
        main()
    except (Stop, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt, EOFError) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        sys.exit(1)
