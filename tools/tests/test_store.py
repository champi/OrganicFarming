"""File-level safety: atomic replace and the cross-process lock."""
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import farmdb  # noqa: F401
from farmdb import store
from farmdb.errors import FarmError


class AtomicWrite(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "farm.sql"
        self.path.write_text("original\n")

    def test_replaces_content(self):
        store.atomic_write(self.path, "new\n")
        self.assertEqual(self.path.read_text(), "new\n")

    def test_creates_missing_file(self):
        p = self.dir / "fresh.sql"
        store.atomic_write(p, "x\n")
        self.assertEqual(p.read_text(), "x\n")

    def test_crash_during_write_keeps_original_and_leaves_no_temp(self):
        real_fsync = os.fsync

        def boom(fd):
            raise OSError("disk full")
        with mock.patch.object(store.os, "fsync", boom):
            with self.assertRaises(OSError):
                store.atomic_write(self.path, "half-written garbage")
        os.fsync = real_fsync
        self.assertEqual(self.path.read_text(), "original\n")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["farm.sql"])

    def test_text_is_written_exactly(self):
        text = "a\r\nb\né\U0001F331\n"
        store.atomic_write(self.path, text)
        self.assertEqual(self.path.read_bytes(), text.encode("utf-8"))


def _hold_lock(path, seconds, ready):
    with store.lock(Path(path), timeout=5):
        ready.set()
        time.sleep(seconds)


class Lock(unittest.TestCase):
    def test_second_holder_waits_for_first(self):
        path = Path(tempfile.mkdtemp()) / ".farm.lock"
        ready = multiprocessing.Event()
        p = multiprocessing.Process(target=_hold_lock, args=(str(path), 0.5, ready))
        p.start()
        ready.wait(5)
        start = time.monotonic()
        with store.lock(path, timeout=5):
            waited = time.monotonic() - start
        p.join()
        self.assertGreater(waited, 0.3)

    def test_gives_up_after_timeout(self):
        path = Path(tempfile.mkdtemp()) / ".farm.lock"
        ready = multiprocessing.Event()
        p = multiprocessing.Process(target=_hold_lock, args=(str(path), 2, ready))
        p.start()
        ready.wait(5)
        with self.assertRaises(FarmError):
            with store.lock(path, timeout=0.3):
                pass
        p.join()


if __name__ == "__main__":
    unittest.main()
