"""Publishing safety tests: mocked Git/GitHub only; no commits or network."""
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location(
    'publish_local', Path(__file__).resolve().parents[1] / 'scripts/publish_local.py')
pub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pub)


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        monkeypatch.delenv(name, raising=False)
    return pub.Publisher(tmp_path)


@pytest.mark.parametrize('name', [
    'build/x', 'dist/AppForge-1.0.0-x86_64.AppImage', 'roadmap.md', 'AGENTS.md',
    'development-instructions.md', 'releases/old.md', '.git/config',
    'src/.env.production', 'src/.envrc', 'docs/secrets/data.txt', 'scripts/private.key',
    'tests/__pycache__/x.pyc', 'src/build/x', 'src/.aws/credentials',
    'src/archive.tar.gz', 'requirements-private.txt'])
def test_policy_excludes_private_and_generated(name):
    assert not pub.allowed(name)


@pytest.mark.parametrize('name', ['.gitignore', 'README.md', 'pyproject.toml',
    'requirements-dev.txt', 'src/appforge/core/discovery.py', 'docs/PUBLISHING.md',
    'scripts/publish_local.py', 'tests/test_publish.py', 'packaging/AppRun',
    'releases/RELEASE_NOTES_v1.2.3.md'])
def test_policy_approves_public_paths(name):
    assert pub.allowed(name)


def test_semver_numeric_prerelease_and_metadata():
    values = ['1.0.0', '0.10.0', '0.9.9', '1.0.0-rc.10', '1.0.0-rc.2',
              '1.0.0-alpha.2', '1.0.0-alpha', '1.0.0-2', '1.0.0-alpha.1']
    ordered = sorted(values, key=functools.cmp_to_key(pub.compare_versions))
    assert ordered == ['0.9.9', '0.10.0', '1.0.0-2', '1.0.0-alpha',
                       '1.0.0-alpha.1', '1.0.0-alpha.2', '1.0.0-rc.2',
                       '1.0.0-rc.10', '1.0.0']
    assert pub.compare_versions('1.0.0+abc', '1.0.0+xyz') == 0
    for value in ('01.0.0', '1.0', '1.0.0-01'):
        with pytest.raises(pub.Stop):
            pub.semver(value)


def test_plan_preserves_files_and_rejects_nested_symlink(publisher, monkeypatch):
    root = publisher.root
    for name in ('src/main.py', 'build/output', 'releases/old.md', '.gitignore'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('example')
    (root / 'src/link.py').symlink_to(root / 'build/output')
    tracked = ['src/main.py', 'build/output', 'releases/old.md', '.gitignore']
    def names(*args):
        if '--ignored' in args:
            return ['build/output', 'releases/old.md']
        if '--others' in args:
            return ['src/link.py']
        return tracked
    monkeypatch.setattr(publisher, 'names', names)
    remove, stage = publisher.plan()
    assert remove == ['build/output', 'releases/old.md']
    assert stage == ['.gitignore', 'src/main.py']
    assert (root / 'build/output').read_text() == 'example'
    assert (root / 'src/link.py').is_symlink()


def test_dry_run_never_calls_mutating_or_network_commands(publisher, monkeypatch, capsys):
    publisher.dry_run = True
    monkeypatch.setattr(publisher, 'identity', lambda: None)
    monkeypatch.setattr(publisher, 'plan', lambda: (['build/output'], ['README.md']))
    def forbidden(*args, **kwargs):
        pytest.fail('Dry run attempted a Git write/network/confirmation')
    for method in ('git', 'check_remote', 'confirm', 'run'):
        monkeypatch.setattr(publisher, method, forbidden)
    publisher.push()
    assert 'DRY RUN' in capsys.readouterr().out


def test_remote_change_stops_before_staging(publisher, monkeypatch):
    calls = []
    def git(*args):
        calls.append(args)
        if args[0] == 'rev-parse':
            return 'old' if len(calls) == 1 else 'new'
        return ''
    monkeypatch.setattr(publisher, 'git', git)
    with pytest.raises(pub.Stop, match='Remote main changed'):
        publisher.check_remote()
    assert not any(c[0] in ('add', 'rm', 'commit', 'push') for c in calls)


def test_divergence_stops(publisher, monkeypatch):
    monkeypatch.setattr(publisher, 'git', lambda *args: 'tip')
    monkeypatch.setattr(publisher, 'run', lambda args, **kw:
                        subprocess.CompletedProcess(args, 1, b'', b''))
    with pytest.raises(pub.Stop, match='ahead or diverged'):
        publisher.check_remote()


def test_confirmation_rejection_never_commits_or_pushes(publisher, monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, 'identity', lambda: None)
    monkeypatch.setattr(publisher, 'check_remote', lambda: setattr(publisher, 'remote_tip', 'tip'))
    monkeypatch.setattr(publisher, 'plan', lambda: (['build/output'], ['README.md']))
    monkeypatch.setattr(publisher, 'names', lambda *args: [])
    monkeypatch.setattr(publisher, 'git', lambda *args: calls.append(args) or 'snapshot')
    def reject(*args):
        raise pub.Stop('Cancelled')
    monkeypatch.setattr(publisher, 'confirm', reject)
    with pytest.raises(pub.Stop, match='Cancelled'):
        publisher.push()
    assert ('rm', '--cached', '--', 'build/output') in calls
    assert not any(c[0] in ('commit', 'push') for c in calls)


def configure_asset(publisher, version='0.10.0'):
    root = publisher.root
    (root / 'dist').mkdir(exist_ok=True)
    (root / 'src/appforge').mkdir(parents=True, exist_ok=True)
    (root / 'pyproject.toml').write_text(f'[project]\nversion = "{version}"\n')
    (root / 'src/appforge/__init__.py').write_text(f'__version__ = "{version}"\n')
    path = root / 'dist' / f'AppForge-{version}-x86_64.AppImage'
    path.write_bytes(b'fixture AppImage bytes')
    notes = root / 'releases' / f'RELEASE_NOTES_v{version}.md'
    notes.parent.mkdir(exist_ok=True)
    notes.write_text(f'# AppForge {version}\n\n## Bug fixes\n- Verified fixture change.\n')
    return path


def test_highest_version_is_numeric_and_project_match(publisher):
    expected = configure_asset(publisher)
    (publisher.root / 'dist/AppForge-0.9.9-x86_64.AppImage').write_bytes(b'older')
    assert publisher.select_release() == ('0.10.0', expected)
    (publisher.root / 'dist/AppForge-0.11.0-x86_64.AppImage').write_bytes(b'newer')
    with pytest.raises(pub.Stop, match='version declarations'):
        publisher.select_release()


def test_empty_and_tied_assets_stop(publisher):
    path = configure_asset(publisher, '1.0.0+one')
    other = path.with_name('AppForge-1.0.0+two-x86_64.AppImage')
    other.write_bytes(b'different build')
    with pytest.raises(pub.Stop, match='equal SemVer'):
        publisher.select_release()
    other.unlink()  # isolated test fixture only
    path.write_bytes(b'')
    with pytest.raises(pub.Stop, match='empty'):
        publisher.select_release()


def record(publisher, monkeypatch):
    path = configure_asset(publisher)
    commit = 'a' * 40
    monkeypatch.setattr(publisher, 'git', lambda *args:
                        commit if args == ('rev-parse', 'HEAD') else
                        'tree' if args == ('rev-parse', 'HEAD^{tree}') else '')
    monkeypatch.setattr(publisher, 'names', lambda *args: [])
    monkeypatch.setattr(publisher, 'identity', lambda: None)
    monkeypatch.setattr(publisher, 'remote_release', lambda tag: False)
    monkeypatch.setattr(publisher, 'run', lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, b'', b''))
    log = publisher.root / 'dist/tests.log'
    log.write_text('Passing controlled build tests and artifact selftest fixture')
    evidence = {'passed': True, 'exit_code': 0, 'log': log.name, 'sha256': pub.sha256(log)}
    data = {'schema': 1, 'asset': path.name, 'version': '0.10.0',
            'source_commit': commit, 'source_tree': 'tree', 'sha256': pub.sha256(path),
            'tests': evidence, 'appimage_selftest': evidence.copy()}
    sidecar = Path(str(path) + '.provenance.json')
    sidecar.write_text(json.dumps(data))
    return path, sidecar, data


def test_missing_provenance_fails_closed(publisher):
    path = configure_asset(publisher)
    with pytest.raises(pub.Stop, match='Cannot confirm'):
        publisher.provenance('0.10.0', path)


def test_provenance_checks_hash_tests_commit_and_logs(publisher, monkeypatch):
    path, sidecar, data = record(publisher, monkeypatch)
    assert publisher.provenance('0.10.0', path)[0] == 'a' * 40
    for key, value in [('sha256', 'wrong'), ('source_commit', 'b' * 40)]:
        broken = {**data, key: value}
        sidecar.write_text(json.dumps(broken))
        with pytest.raises(pub.Stop):
            publisher.provenance('0.10.0', path)
    sidecar.write_text(json.dumps({**data, 'tests': {**data['tests'], 'passed': False}}))
    with pytest.raises(pub.Stop, match='passing tests'):
        publisher.provenance('0.10.0', path)
    sidecar.write_text(json.dumps(data))
    (publisher.root / 'dist/tests.log').write_text('changed')
    with pytest.raises(pub.Stop, match='changed tests log'):
        publisher.provenance('0.10.0', path)


def test_existing_release_never_overwritten(publisher, monkeypatch):
    monkeypatch.setattr(publisher, 'git', lambda *args: '')
    monkeypatch.setattr(publisher, 'run', lambda args: subprocess.CompletedProcess(
        args, 0, json.dumps([[{'tag_name': 'v1.0.0'}]]).encode(), b''))
    with pytest.raises(pub.Stop, match='already exists'):
        publisher.remote_release('v1.0.0')


def test_existing_tag_never_moved(publisher, monkeypatch):
    monkeypatch.setattr(publisher, 'git', lambda *args:
                        'other\trefs/tags/v1.0.0' if args[0] == 'ls-remote' else 'current')
    monkeypatch.setattr(publisher, 'run', lambda args: subprocess.CompletedProcess(args, 0, b'[[]]', b''))
    with pytest.raises(pub.Stop, match='will not be moved'):
        publisher.remote_release('v1.0.0')


def test_manual_build_dry_run_does_not_require_missing_provenance(publisher, monkeypatch, capsys):
    configure_asset(publisher)
    publisher.dry_run = True
    monkeypatch.setattr(publisher, 'push', lambda: None)
    monkeypatch.setattr(publisher, 'run', lambda *a, **k: pytest.fail('Offline preview used network'))
    monkeypatch.setattr(publisher, 'confirm', lambda *a: pytest.fail('Offline preview asked approval'))
    publisher.release()
    assert 'local release checks passed' in capsys.readouterr().out


def test_secret_detection_does_not_print_secret(publisher):
    secret = b'ghp_' + b'a' * 30
    with pytest.raises(pub.Stop) as exc:
        publisher.check_content('src/config.py', secret)
    assert secret.decode() not in str(exc.value)


def test_confirmed_push_uses_only_cached_removal_and_explicit_ref(publisher, monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, 'identity', lambda: None)
    monkeypatch.setattr(publisher, 'check_remote', lambda: setattr(publisher, 'remote_tip', 'tip'))
    monkeypatch.setattr(publisher, 'plan', lambda: (['build/output'], ['README.md']))
    monkeypatch.setattr(publisher, 'names', lambda *args: ['README.md'])
    monkeypatch.setattr(publisher, 'confirm', lambda *args: None)
    monkeypatch.setattr('builtins.input', lambda *args: 'Describe the public changes')
    def git(*args):
        calls.append(args)
        if args == ('write-tree',) or args == ('rev-parse', 'HEAD^{tree}'):
            return 'tree'
        if args == ('rev-parse', 'HEAD'):
            return 'head'
        if args[0] == 'ls-remote':
            return 'tip\trefs/heads/main'
        return ''
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1 if args == ['git', 'diff', '--cached', '--quiet']
                                           else 0, b'public contents', b'')
    monkeypatch.setattr(publisher, 'git', git)
    monkeypatch.setattr(publisher, 'run', run)
    publisher.push()
    assert ('rm', '--cached', '--', 'build/output') in calls
    assert ('add', '--', 'README.md') in calls
    assert ('commit', '-m', 'Describe the public changes') in calls
    assert publisher.remote_tip == 'head'
    assert ('-c', 'push.followTags=false', 'push', '--no-force', '--no-follow-tags',
            'origin', 'HEAD:refs/heads/main') in calls
    assert not any('--force' in call or '--hard' in call for call in calls)


@pytest.mark.parametrize('with_record', [False, True])
def test_confirmed_release_uploads_only_asset_to_exact_commit(publisher, monkeypatch, with_record):
    asset, sidecar, _ = record(publisher, monkeypatch)
    if not with_record:
        sidecar.unlink()  # isolated fixture: ordinary manually built AppImage
    calls = []
    monkeypatch.setattr(publisher, 'push', lambda: calls.append(['source-push']))
    monkeypatch.setattr(publisher, 'confirm', lambda *args: None)
    monkeypatch.setattr(publisher, 'remote_unchanged', lambda: None)
    monkeypatch.setattr(publisher, 'remote_release', lambda tag: False)
    def run(args, **kwargs):
        calls.append(args)
        data = {'url': 'https://github.com/Thilen03/AppForge/releases/tag/v0.10.0',
                'tagName': 'v0.10.0',
                'body': (publisher.root / 'releases/RELEASE_NOTES_v0.10.0.md').read_text(), 'assets': [{'name': asset.name,
                    'size': asset.stat().st_size, 'digest': 'sha256:' + pub.sha256(asset)}]}
        return subprocess.CompletedProcess(args, 0, json.dumps(data).encode(), b'')
    monkeypatch.setattr(publisher, 'run', run)
    publisher.release()
    create = next(call for call in calls if call[:3] == ['gh', 'release', 'create'])
    assert create == ['gh', 'release', 'create', 'v0.10.0', str(asset), '--repo', pub.REPO,
                      '--title', 'AppForge 0.10.0', '--notes-file',
                      str(publisher.root / 'releases/RELEASE_NOTES_v0.10.0.md'),
                      '--target', 'a' * 40]
    assert calls[0] == ['gh', 'auth', 'status']
    assert calls[1] == ['source-push']
    assert not any('--clobber' in call for call in calls)


def test_no_release_when_confirmation_declined(publisher, monkeypatch):
    record(publisher, monkeypatch)
    monkeypatch.setattr(publisher, 'push', lambda: None)
    monkeypatch.setattr(publisher, 'remote_release', lambda tag: False)
    calls = []
    monkeypatch.setattr(publisher, 'run', lambda args:
        calls.append(args) or subprocess.CompletedProcess(args, 0, b'', b''))
    def reject(*args):
        raise pub.Stop('Cancelled')
    monkeypatch.setattr(publisher, 'confirm', reject)
    with pytest.raises(pub.Stop, match='Cancelled'):
        publisher.release()
    assert calls == [['gh', 'auth', 'status']]


def test_readonly_metadata_is_reported_without_write_probe(publisher, monkeypatch):
    def git(*args):
        if args == ('rev-parse', '--show-toplevel'):
            return str(publisher.root)
        if args == ('symbolic-ref', '--short', 'HEAD'):
            return 'main'
        if args == ('rev-parse', '--abbrev-ref', '@{upstream}'):
            return 'origin/main'
        if args == ('rev-parse', '--absolute-git-dir'):
            return str(publisher.root / '.git')
        return next(iter(pub.URLS))
    monkeypatch.setattr(publisher, 'git', git)
    monkeypatch.setattr(pub.os, 'access', lambda *args: False)
    with pytest.raises(pub.Stop, match='read-only'):
        publisher.identity()


def test_push_failure_is_reported_without_success(publisher, monkeypatch, capsys):
    monkeypatch.setattr(publisher, 'identity', lambda: None)
    monkeypatch.setattr(publisher, 'check_remote', lambda: setattr(publisher, 'remote_tip', 'tip'))
    monkeypatch.setattr(publisher, 'plan', lambda: ([], []))
    monkeypatch.setattr(publisher, 'names', lambda *args: [])
    monkeypatch.setattr(publisher, 'confirm', lambda *args: None)
    monkeypatch.setattr(publisher, 'remote_unchanged', lambda: None)
    def git(*args):
        if 'push' in args:
            raise pub.Stop('Push rejected')
        return 'snapshot'
    monkeypatch.setattr(publisher, 'git', git)
    monkeypatch.setattr(publisher, 'run', lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, b'', b''))
    with pytest.raises(pub.Stop, match='Push rejected'):
        publisher.push()
    assert 'Source push succeeded' not in capsys.readouterr().out


@pytest.mark.parametrize('name', [
    'releases/private.md', 'releases/RELEASE_NOTES_v1.2.md',
    'releases/RELEASE_NOTES_v01.2.3.md',
    'releases/internal/RELEASE_NOTES_v1.2.3.md',
    'docs/RELEASE_NOTES_v1.2.3.md', 'RELEASE_NOTES_v1.2.3.md',
    'releases/AGENTS.md', 'releases/.env'])
def test_public_release_notes_allowlist_is_narrow(name):
    assert not pub.allowed(name)


def test_valid_release_notes_are_staged_and_historical_notes_preserved(publisher, monkeypatch):
    path = publisher.root / 'releases/RELEASE_NOTES_v0.5.4.md'
    path.parent.mkdir()
    path.write_text('# AppForge 0.5.4\n\nHistorical notes remain.\n')
    original = path.read_bytes()
    monkeypatch.setattr(publisher, 'names', lambda *args:
                        [] if '--ignored' in args or '--others' in args else
                        ['releases/RELEASE_NOTES_v0.5.4.md'])
    assert publisher.plan() == ([], ['releases/RELEASE_NOTES_v0.5.4.md'])
    assert path.read_bytes() == original


def test_missing_notes_stop_before_source_push(publisher, monkeypatch):
    configure_asset(publisher)
    (publisher.root / 'releases/RELEASE_NOTES_v0.10.0.md').unlink()
    monkeypatch.setattr(publisher, 'push', lambda: pytest.fail('Must not push without notes'))
    monkeypatch.setattr(publisher, 'confirm', lambda *args: pytest.fail('Missing notes'))
    with pytest.raises(pub.Stop, match='missing or empty'):
        publisher.release()


def test_wrong_notes_heading_and_symlink_stop(publisher):
    configure_asset(publisher)
    path = publisher.root / 'releases/RELEASE_NOTES_v0.10.0.md'
    path.write_text('# AppForge 0.9.9\n\nWrong version\n')
    with pytest.raises(pub.Stop, match='version heading'):
        publisher.release_notes('0.10.0')
    path.unlink()
    path.symlink_to(publisher.root / 'pyproject.toml')
    with pytest.raises(pub.Stop, match='symlinks'):
        publisher.release_notes('0.10.0')


def test_manual_approval_binds_exact_version_and_hash(publisher, monkeypatch, capsys):
    asset, _, _ = record(publisher, monkeypatch)
    words = []
    def confirm(word, description):
        words.append(word)
        raise pub.Stop('Stopped after presenting testing prompt')
    monkeypatch.setattr(publisher, 'confirm', confirm)
    monkeypatch.setattr(publisher, 'push', lambda: None)
    with pytest.raises(pub.Stop, match='testing prompt'):
        publisher.release()
    assert words == ['RELEASE']
    output = capsys.readouterr().out
    assert asset.name in output and pub.sha256(asset) in output


def test_notes_change_during_push_invalidates_approval(publisher, monkeypatch):
    record(publisher, monkeypatch)
    monkeypatch.setattr(publisher, 'confirm', lambda *args: None)
    path = publisher.root / 'releases/RELEASE_NOTES_v0.10.0.md'
    monkeypatch.setattr(publisher, 'push', lambda: path.write_text(
        '# AppForge 0.10.0\n\nChanged after approval\n'))
    calls = []
    monkeypatch.setattr(publisher, 'run', lambda args, **kw:
        calls.append(args) or subprocess.CompletedProcess(args, 0, b'', b''))
    with pytest.raises(pub.Stop, match='notes changed'):
        publisher.release()


def test_release_dry_run_never_assumes_manual_approval(publisher, monkeypatch, capsys):
    record(publisher, monkeypatch)
    publisher.dry_run = True
    monkeypatch.setattr(publisher, 'push', lambda: None)
    monkeypatch.setattr(publisher, 'confirm', lambda *args: pytest.fail('Dry run prompted'))
    monkeypatch.setattr(publisher, 'run', lambda *args: pytest.fail('Dry run used GitHub'))
    publisher.release()
    assert 'No publishing or testing approval assumed' in capsys.readouterr().out


def test_authentication_failure_occurs_before_any_confirmation_or_push(publisher, monkeypatch):
    asset, sidecar, _ = record(publisher, monkeypatch)
    sidecar.unlink()
    monkeypatch.setattr(publisher, 'confirm', lambda *a: pytest.fail('Must check authentication first'))
    monkeypatch.setattr(publisher, 'push', lambda: pytest.fail('Must check authentication first'))
    def fail_auth(args, **kwargs):
        raise pub.Stop('GitHub authentication failed')
    monkeypatch.setattr(publisher, 'run', fail_auth)
    with pytest.raises(pub.Stop, match='authentication failed'):
        publisher.release()


def test_supplied_invalid_provenance_is_not_ignored(publisher, monkeypatch):
    asset, sidecar, data = record(publisher, monkeypatch)
    sidecar.write_text(json.dumps({**data, 'sha256': 'wrong'}))
    monkeypatch.setattr(publisher, 'confirm', lambda *a: pytest.fail('Invalid record needs fixing first'))
    monkeypatch.setattr(publisher, 'push', lambda: pytest.fail('Invalid record needs fixing first'))
    with pytest.raises(pub.Stop, match='hash does not match'):
        publisher.release()


def test_release_conflict_checked_before_source_push_and_approval(publisher, monkeypatch):
    asset, sidecar, data = record(publisher, monkeypatch)
    sidecar.unlink()
    def conflict(tag):
        raise pub.Stop('Release already exists')
    monkeypatch.setattr(publisher, 'remote_release', conflict)
    monkeypatch.setattr(publisher, 'push', lambda: pytest.fail('Conflict should stop first'))
    monkeypatch.setattr(publisher, 'confirm', lambda *a: pytest.fail('Conflict should stop first'))
    with pytest.raises(pub.Stop, match='already exists'):
        publisher.release()


def test_mutation_after_release_confirmation_prevents_upload(publisher, monkeypatch):
    asset, sidecar, _ = record(publisher, monkeypatch)
    sidecar.unlink()
    monkeypatch.setattr(publisher, 'push', lambda: None)
    monkeypatch.setattr(publisher, 'remote_unchanged', lambda: None)
    monkeypatch.setattr(publisher, 'confirm', lambda *a: asset.write_bytes(b'changed after approval'))
    calls = []
    monkeypatch.setattr(publisher, 'run', lambda args, **kw:
        calls.append(args) or subprocess.CompletedProcess(args, 0, b'', b''))
    with pytest.raises(pub.Stop, match='Approval is invalid'):
        publisher.release()
    assert calls == [['gh', 'auth', 'status']]


def test_source_advance_from_successful_push_is_expected(publisher, monkeypatch):
    # Source push advances origin; release must use the updated expected tip.
    monkeypatch.setattr(publisher, 'git', lambda *args: 'new-commit\trefs/heads/main')
    publisher.remote_tip = 'new-commit'
    publisher.remote_unchanged()  # no false divergence error for our own push
