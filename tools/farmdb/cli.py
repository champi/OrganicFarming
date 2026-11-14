"""bin/farm: the only supported way to change data/farm.sql.

  farm query  SQL|-          read-only, prints CSV
  farm exec   -m MSG SQL|-   data change: validated, saved, committed, pushed
  farm migrate [-m MSG]      apply pending data/migrations/*.sql, commit, push
  farm check  [--staged]     integrity, foreign keys, STRICT, migration checksums

Exit codes: 0 ok, 1 refused/failed (nothing changed), 2 usage error,
            3 saved and committed but the push failed.
"""
import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import db, gitops, migrations as mig, store
from .errors import FarmError

PUSH_FAILED = 3
_READ_ACTIONS = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
                 sqlite3.SQLITE_RECURSIVE}


def repo_root():
    return Path(os.environ.get("FARM_ROOT") or Path(__file__).resolve().parents[2])


def _sql_arg(value):
    return sys.stdin.read() if value == "-" else value


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _refuse_if_edited_outside(root):
    if gitops.is_dirty(root, store.SQL_REL):
        raise FarmError(f"{store.SQL_REL} has changes made outside bin/farm. "
                        f"Undo them with: git restore --staged --worktree {store.SQL_REL}")


def _verify(text, files):
    """Re-load what is about to be saved and check it from scratch."""
    conn = db.load(text)
    found = db.check(conn) + mig.problems(conn, files)
    if found:
        raise FarmError("refusing to save, result has problems: " + "; ".join(found))


def _save_commit_push(root, old_text, new_text, extra_paths, message):
    path = Path(root) / store.SQL_REL
    existed = path.exists()
    store.atomic_write(path, new_text)
    try:
        sha = gitops.commit(root, [store.SQL_REL, *extra_paths], message)
    except FarmError:
        if existed:
            store.atomic_write(path, old_text)
        else:
            path.unlink(missing_ok=True)
        raise
    print(f"saved and committed {sha[:10]}")
    ok, output = gitops.push(root)
    if not ok:
        print(f"warning: committed locally but git push failed:\n{output}", file=sys.stderr)
        return PUSH_FAILED
    print("pushed")
    return 0


def cmd_exec(root, args):
    message = args.message.strip()
    if not message:
        raise FarmError("a commit message (-m) is required")
    sql = _sql_arg(args.sql)
    with store.lock(gitops.lock_path(root)):
        _refuse_if_edited_outside(root)
        text, files = store.read_sql(root), store.read_migrations(root)
        conn = db.load(text)
        found = db.check(conn) + mig.problems(conn, files)
        if found:
            raise FarmError("the saved database has problems; fix them first: " + "; ".join(found))
        waiting = mig.pending(conn, files)
        if waiting:
            raise FarmError("apply pending migrations first (bin/farm migrate): "
                            + ", ".join(waiting))
        db.execute_write(conn, sql)
        new_text = db.dump(conn)
        if new_text == text:
            print("no changes; nothing committed")
            return 0
        _verify(new_text, files)
        return _save_commit_push(root, text, new_text, [], message)


def cmd_migrate(root, args):
    with store.lock(gitops.lock_path(root)):
        _refuse_if_edited_outside(root)
        text, files = store.read_sql(root), store.read_migrations(root)
        conn = db.load(text)
        found = db.check(conn)
        if found:
            raise FarmError("the saved database has problems; fix them first: " + "; ".join(found))
        applied = mig.apply_pending(conn, files, _now())
        if not applied:
            print("nothing to apply")
            return 0
        new_text = db.dump(conn)
        _verify(new_text, files)
        message = (args.message or "").strip() or "Apply migration " + ", ".join(applied)
        print("applied: " + ", ".join(applied))
        return _save_commit_push(root, text, new_text,
                                 [f"{store.MIGRATIONS_REL}/{n}" for n in applied], message)


def cmd_query(root, args):
    pieces = [s for s in db.split_statements(_sql_arg(args.sql)) if s.strip().strip(";").strip()]
    if len(pieces) != 1:
        raise FarmError("query takes exactly one SQL statement")
    conn = db.load(store.read_sql(root))
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _READ_ACTIONS
                        else sqlite3.SQLITE_DENY)
    try:
        cursor = conn.execute(pieces[0])
        rows = cursor.fetchall()
    except sqlite3.Error as e:
        raise FarmError(f"query refused or failed (queries are read-only): {e}") from e
    out = csv.writer(sys.stdout, lineterminator="\n")
    if cursor.description:
        out.writerow([d[0] for d in cursor.description])
    for row in rows:
        out.writerow(["" if v is None else v.hex() if isinstance(v, bytes) else v for v in row])
    return 0


def cmd_check(root, args):
    if args.staged:
        text = gitops.show_staged(root, store.SQL_REL) or ""
        files = {}
        for rel in gitops.list_staged(root, store.MIGRATIONS_REL):
            name = rel.rsplit("/", 1)[-1]
            if not name.startswith("."):
                files[name] = gitops.show_staged(root, rel) or ""
    else:
        text, files = store.read_sql(root), store.read_migrations(root)
    try:
        conn = db.load(text)
    except FarmError as e:
        found = [str(e)]
    else:
        found = db.check(conn) + mig.problems(conn, files)
        for name in mig.pending(conn, files):
            print(f"note: migration {name} is not applied yet (bin/farm migrate)")
    for problem in found:
        print(f"problem: {problem}")
    if found:
        return 1
    print("ok")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="farm", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("query", help="read-only SQL, prints CSV")
    q.add_argument("sql", help="SQL text, or - to read stdin")
    e = sub.add_parser("exec", help="change data: validate, save, commit, push")
    e.add_argument("-m", "--message", required=True, help="commit message")
    e.add_argument("sql", help="SQL text, or - to read stdin")
    m = sub.add_parser("migrate", help="apply pending migrations, commit, push")
    m.add_argument("-m", "--message", help="commit message")
    c = sub.add_parser("check", help="check the database and migrations")
    c.add_argument("--staged", action="store_true", help="check the git index (pre-commit)")
    return p


COMMANDS = {"exec": cmd_exec, "migrate": cmd_migrate, "query": cmd_query, "check": cmd_check}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](repo_root(), args)
    except FarmError as e:
        print(f"farm: {e}", file=sys.stderr)
        return 1
