"""Files on disk: where things live, crash-safe replacement, and the cross-process lock."""
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import FarmError

SQL_REL = "data/farm.sql"
MIGRATIONS_REL = "data/migrations"


def read_sql(root):
    path = Path(root) / SQL_REL
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_migrations(root):
    folder = Path(root) / MIGRATIONS_REL
    if not folder.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())
            if p.is_file() and not p.name.startswith(".")}


def atomic_write(path, text):
    """Replace path with text so readers see either the old or the new file, never half."""
    path = Path(path)
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp, path)
    except BaseException:
        if fd is not None:
            os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


@contextmanager
def lock(path, timeout=60.0):
    """Exclusive lock shared by every bin/farm process writing to this repo."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise FarmError("another bin/farm operation is still running; try again")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
