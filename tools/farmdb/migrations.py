"""Numbered schema migrations (data/migrations/NNN_name.sql), applied once, in order.

Applied migrations are recorded with a checksum in the schema_migrations table, which
lives inside the dump, so tampering with an applied file is detectable later.
"""
import hashlib
import re
import sqlite3

from . import db
from .errors import FarmError

NAME_RE = re.compile(r"(\d{3,})_[a-z0-9]+(?:_[a-z0-9]+)*\.sql")

_DENIED = {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT, sqlite3.SQLITE_PRAGMA,
           sqlite3.SQLITE_ANALYZE,
           sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
_WRITES = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}

_CREATE_TABLE = """CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT, WITHOUT ROWID"""


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse(files):
    entries, errors, seen = [], [], {}
    for name in files:
        m = NAME_RE.fullmatch(name)
        if not m:
            errors.append(f"bad migration file name {name!r} (expected NNN_lower_words.sql)")
            continue
        number = int(m.group(1))
        if number in seen:
            errors.append(f"migrations {seen[number]} and {name} share number {number}")
        seen[number] = name
        entries.append((number, name))
    return sorted(entries), errors


def applied(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='schema_migrations'").fetchone()
    if not exists:
        return {}
    return dict(conn.execute("SELECT name, sha256 FROM schema_migrations"))


def pending(conn, files):
    done = applied(conn)
    entries, _ = _parse(files)
    return [name for _, name in entries if name not in done]


def problems(conn, files):
    done = applied(conn)
    entries, errors = _parse(files)
    for name, digest in sorted(done.items()):
        if name not in files:
            errors.append(f"applied migration {name} is missing from data/migrations")
        elif sha256(files[name]) != digest:
            errors.append(f"applied migration {name} has been changed since it was applied")
    numbers = {name: number for number, name in entries}
    highest = max((numbers[n] for n in done if n in numbers), default=None)
    for number, name in entries:
        if name not in done and highest is not None and number < highest:
            errors.append(f"new migration {name} is numbered older than an applied one; "
                          "renumber it after the latest")
    return errors


def apply_pending(conn, files, now):
    """Apply all pending migrations in one all-or-nothing run. Returns names applied."""
    errors = problems(conn, files)
    if errors:
        raise FarmError("; ".join(errors))
    todo = pending(conn, files)
    if not todo:
        return []

    current = [None]
    actions = [0]

    def authorizer(action, arg1, arg2, dbname, source):
        actions[0] += 1
        if action in _DENIED:
            return sqlite3.SQLITE_DENY
        if action in _WRITES and source is None and (arg1 or "").lower() == "schema_migrations":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    # Foreign keys off for the run so table rebuilds work (SQLite's documented
    # procedure); a full foreign_key_check runs before committing.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(_CREATE_TABLE)
        for name in todo:
            current[0] = name
            actions[0] = 0
            conn.set_authorizer(authorizer)
            try:
                for statement in db.split_statements(files[name]):
                    conn.execute(statement).fetchall()
            finally:
                conn.set_authorizer(None)
            if actions[0] == 0:
                raise FarmError("contains no SQL statements")
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)",
                         (name, sha256(files[name]), now))
        current[0] = None
        found = db.check(conn)
        if found:
            raise FarmError("; ".join(found))
        conn.execute("COMMIT")
    except (sqlite3.Error, FarmError) as e:
        conn.set_authorizer(None)
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        where = f"migration {current[0]}" if current[0] else "migrations"
        raise FarmError(f"{where} rejected, nothing applied: {e}") from e
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise FarmError("could not re-enable foreign key enforcement")
    return todo
