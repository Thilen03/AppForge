"""v0.5.3: single instance, own launcher (taskbar pinning) and in-place self-update. Qt-free."""
import json
import multiprocessing
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appforge.core import selfupdate
from appforge.core.desktop import selflauncher
from appforge.core.instance import InstanceGuard
from appforge.core.updates.github import Asset, Release


def _second_launch(lock, sock, q):
    q.put(InstanceGuard(lock, sock).acquire(["/x/Some.AppImage"], wait=3))


class InstanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="afi-")
        self.lock = os.path.join(self.tmp, "a.lock")
        self.sock = os.path.join(self.tmp, "a.sock")

    def test_second_launch_signals_first_and_exits(self):
        first = InstanceGuard(self.lock, self.sock)
        self.assertTrue(first.acquire())
        got = []
        first.serve(got.append)
        q = multiprocessing.Queue()
        p = multiprocessing.Process(target=_second_launch, args=(self.lock, self.sock, q))
        p.start()
        self.assertFalse(q.get(timeout=10))            # second instance must NOT become primary
        p.join(5)
        deadline = time.time() + 3
        while not got and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(got, [["/x/Some.AppImage"]])
        first.release()

    def test_slot_is_free_after_release_and_after_crash_lock_semantics(self):
        a = InstanceGuard(self.lock, self.sock)
        self.assertTrue(a.acquire())
        a.release()
        b = InstanceGuard(self.lock, self.sock)
        self.assertTrue(b.acquire())                   # e.g. restart after a self-update
        b.release()

    def test_stale_socket_file_is_replaced(self):
        Path(self.sock).write_text("junk")
        g = InstanceGuard(self.lock, self.sock)
        self.assertTrue(g.acquire())
        g.serve(lambda a: None)
        g.release()

    def test_unresponsive_primary_is_not_duplicated(self):
        a = InstanceGuard(self.lock, self.sock)
        self.assertTrue(a.acquire())                   # holds the lock but never serve()s
        b = InstanceGuard(self.lock, self.sock)
        self.assertFalse(b.acquire(wait=0.3))
        a.release()


class SelfLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="afl-"))
        os.environ["APPFORGE_DATA_DIR"] = str(self.tmp / "data")
        (self.tmp / "AppForge x.AppImage").write_bytes(b"x")
        self.exe = self.tmp / "AppForge x.AppImage"
        self.icon = self.tmp / "i.png"
        self.icon.write_bytes(b"png")
        self.apps = self.tmp / "apps"

    def test_writes_matching_entry_once(self):
        self.assertTrue(selflauncher.ensure_self_launcher(self.icon, self.exe, self.apps))
        text = (self.apps / "appforge.desktop").read_text()
        self.assertIn("StartupWMClass=appforge", text)
        self.assertIn(f"TryExec={self.exe}", text)
        self.assertIn('Exec="' + str(self.exe), text)       # path contains a space -> quoted
        self.assertIn("Icon=" + str(self.tmp / "data" / "appforge.png"), text)
        self.assertFalse(selflauncher.ensure_self_launcher(self.icon, self.exe, self.apps))  # unchanged

    def test_follows_a_moved_appimage(self):
        selflauncher.ensure_self_launcher(self.icon, self.exe, self.apps)
        moved = self.tmp / "AppForge-new.AppImage"
        moved.write_bytes(b"x")
        self.assertTrue(selflauncher.ensure_self_launcher(self.icon, moved, self.apps))
        self.assertIn(str(moved), (self.apps / "appforge.desktop").read_text())

    def test_foreign_file_is_left_alone(self):
        self.apps.mkdir()
        (self.apps / "appforge.desktop").write_text("[Desktop Entry]\nName=Mine\n")
        self.assertFalse(selflauncher.ensure_self_launcher(self.icon, self.exe, self.apps))
        self.assertIn("Mine", (self.apps / "appforge.desktop").read_text())

    def test_source_run_writes_nothing(self):
        os.environ.pop("APPIMAGE", None)
        self.assertFalse(selflauncher.ensure_self_launcher(self.icon, None, self.apps))
        self.assertFalse(self.apps.exists())


class _Client:
    def __init__(self, releases):
        self._r = releases

    def releases(self, owner, name):
        return self._r


def _rel(tag, **kw):
    assets = [Asset(f"AppForge-{tag.lstrip('v')}-x86_64.AppImage", "https://x/a", 100),
              Asset("SHA256SUMS", "https://x/s", 10)]
    return Release(tag=tag, html_url="https://github.com/Thilen03/AppForge/releases/tag/" + tag,
                   assets=assets, **kw)


class SelfUpdateTests(unittest.TestCase):
    def test_newer_release_carries_the_appimage_asset(self):
        up = selfupdate.check_self_update(_Client([_rel("v0.5.4"), _rel("v0.5.3")]), current="0.5.3")
        self.assertEqual(up.version, "0.5.4")
        self.assertEqual(up.asset["name"], "AppForge-0.5.4-x86_64.AppImage")
        self.assertEqual(len(up.assets), 2)

    def test_up_to_date_and_prereleases_ignored(self):
        self.assertIsNone(selfupdate.check_self_update(_Client([_rel("v0.5.3")]), current="0.5.3"))
        self.assertIsNone(selfupdate.check_self_update(_Client([_rel("v0.9.0", prerelease=True),
                                                                _rel("v0.5.3")]), current="0.5.3"))

    def test_blockers(self):
        up = selfupdate.SelfUpdate("0.5.4", "u", asset={"name": "a", "url": "https://x"})
        os.environ.pop("APPIMAGE", None)
        self.assertIn("AppImage", selfupdate.install_blocker(up))
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "AppForge.AppImage"
        f.write_bytes(b"x")
        os.environ["APPIMAGE"] = str(f)
        self.assertIsNone(selfupdate.install_blocker(up))
        self.assertIn("no AppImage", selfupdate.install_blocker(selfupdate.SelfUpdate("0.5.4", "u")))
        os.environ.pop("APPIMAGE")

    def test_prune_keeps_newest_two(self):
        tmp = Path(tempfile.mkdtemp())
        target = tmp / "AppForge.AppImage"
        target.write_bytes(b"x")
        bdir = tmp / ".AppForge.backups"
        bdir.mkdir()
        for i in range(5):
            p = bdir / f"AppForge-0.{i}.AppImage"
            p.write_bytes(b"x")
            os.utime(p, (1000 + i, 1000 + i))
        selfupdate.prune_backups(target, keep=2)
        self.assertEqual(sorted(p.name for p in bdir.iterdir()),
                         ["AppForge-0.3.AppImage", "AppForge-0.4.AppImage"])


if __name__ == "__main__":
    unittest.main()
