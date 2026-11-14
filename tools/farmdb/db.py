"""Load/dump the database text, check its integrity, and run guarded data writes.

The canonical data is a SQL text dump. Every operation loads it into an in-memory
SQLite database, works there, and (for writes) dumps it back. Nothing is written
to disk here; see store.py.
"""
import sqlite3

from .errors import FarmError

# Tables that only the system itself may write (migration bookkeeping).
PROTECTED_TABLES = {"schema_migrations"}

_A = sqlite3
# Authorizer allowlist for data writes. Anything else (DDL, PRAGMA, ATTACH,
# transaction control, ...) is denied, which fails closed for unknown codes.
_ALLOWED_ACTIONS = {_A.SQLITE_INSERT, _A.SQLITE_UPDATE, _A.SQLITE_DELETE,
                    _A.SQLITE_READ, _A.SQLITE_SELECT, _A.SQLITE_FUNCTION,
                    _A.SQLITE_RECURSIVE}
_WRITE_ACTIONS = {_A.SQLITE_INSERT, _A.SQLITE_UPDATE, _A.SQLITE_DELETE}
_SCHEMA_ACTIONS = {getattr(_A, n) for n in dir(_A)
                   if n.startswith(("SQLITE_CREATE_", "SQLITE_DROP_"))} | {
                   _A.SQLITE_ALTER_TABLE, _A.SQLITE_REINDEX}
_ACTION_NAMES = {getattr(_A, n): n[len("SQLITE_"):] for n in dir(_A)
                 if n.startswith("SQLITE_") and isinstance(getattr(_A, n), int)
                 and n not in ("SQLITE_OK", "SQLITE_DENY", "SQLITE_IGNORE")}


def load(sql_text):
    """Build an in-memory database from dump text. Foreign keys are ON afterwards."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = OFF")  # dump order is by table name, not dependency
    try:
        conn.executescript(sql_text)
    except sqlite3.Error as e:
        conn.close()
        raise FarmError(f"could not load database text: {e}") from e
    if conn.in_transaction:
        conn.close()
        raise FarmError("database text left a transaction open (missing COMMIT?)")
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise FarmError("could not enable foreign key enforcement")
    return conn


def dump(conn):
    return "\n".join(conn.iterdump()) + "\n"


def schema_signature(conn):
    return tuple(conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"))


def check(conn):
    """Return a list of human-readable problems; empty means the database is sound."""
    problems = []
    result = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    if result != ["ok"]:
        problems += [f"integrity: {r}" for r in result]
    for table, rowid, parent, _ in conn.execute("PRAGMA foreign_key_check"):
        problems.append(f"foreign key violation: {table} row {rowid} "
                        f"references a missing row in {parent}")
    for _, name, kind, _, without_rowid, strict in conn.execute("PRAGMA main.table_list"):
        if kind != "table" or name.startswith("sqlite_"):
            continue
        if not strict:
            problems.append(f"table {name} is not STRICT")
        if not without_rowid and not _has_rowid_alias(conn, name):
            problems.append(f"table {name} needs an INTEGER PRIMARY KEY column "
                            "(or WITHOUT ROWID); implicit rowids are renumbered on reload")
    return problems


def _has_rowid_alias(conn, table):
    pk_cols = [r for r in conn.execute(f'PRAGMA table_info("{table}")') if r[5] > 0]
    return len(pk_cols) == 1 and pk_cols[0][2].upper() == "INTEGER"


def split_statements(sql):
    """Split SQL into single statements, respecting quotes, comments and triggers."""
    statements, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            statements.append(buf)
            buf = ""
    if buf.strip():
        statements.append(buf)
    return statements


def execute_write(conn, sql):
    """Run data-changing SQL atomically. Raises FarmError (with no changes) on refusal."""
    before = schema_signature(conn)
    denied = []
    actions = [0]

    def authorizer(action, arg1, arg2, dbname, source):
        actions[0] += 1
        if action not in _ALLOWED_ACTIONS:
            denied.append(action)
            return sqlite3.SQLITE_DENY
        if action in _WRITE_ACTIONS and source is None and arg1 and (
                arg1.lower() in PROTECTED_TABLES or arg1.lower().startswith("sqlite_")):
            denied.append(("protected", arg1))
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.execute("BEGIN")
    conn.set_authorizer(authorizer)
    try:
        for statement in split_statements(sql):
            conn.execute(statement).fetchall()
    except sqlite3.Error as e:
        conn.set_authorizer(None)
        conn.execute("ROLLBACK")
        raise FarmError(_explain(e, denied)) from e
    conn.set_authorizer(None)

    if actions[0] == 0:
        conn.execute("ROLLBACK")
        raise FarmError("no SQL statements to run")
    if schema_signature(conn) != before:  # belt and braces; the authorizer should stop this
        conn.execute("ROLLBACK")
        raise FarmError("schema changes must go through a migration (data/migrations)")
    try:
        conn.execute("COMMIT")  # deferred constraints are checked here
    except sqlite3.Error as e:
        conn.execute("ROLLBACK")
        raise FarmError(f"rejected: {e}") from e


_SCHEMA_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema"}


def _explain(error, denied):
    # DDL shows up as a write to sqlite_master before (or instead of) its CREATE/DROP code.
    if any(d in _SCHEMA_ACTIONS or (isinstance(d, tuple) and d[1].lower() in _SCHEMA_TABLES)
           for d in denied):
        return ("rejected: schema changes must go through a migration "
                "(data/migrations), not a data write")
    for d in denied:
        if isinstance(d, tuple):
            return f"rejected: table {d[1]} is managed by the system and cannot be written"
        if d in _SCHEMA_ACTIONS:
            return ("rejected: schema changes must go through a migration "
                    f"(data/migrations), not a data write [{_ACTION_NAMES.get(d, d)}]")
        return f"rejected: {_ACTION_NAMES.get(d, d)} statements are not allowed in a data write"
    return f"rejected: {error}"
