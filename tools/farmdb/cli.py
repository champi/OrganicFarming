"""bin/farm: the only supported way to change data/farm.sql.

  farm query  SQL|-          read-only, prints CSV
  farm exec   -m MSG SQL|-   data change: validated, saved, committed, pushed
  farm migrate [-m MSG]      apply pending data/migrations/*.sql, commit, push
  farm check  [--staged]     integrity, foreign keys, STRICT, migration checksums

Exit codes: 0 ok, 1 refused/failed (nothing changed), 2 usage error,
            3 saved and committed but the push failed.
"""
import argparse
import base64
import binascii
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import db, gitops, migrations as mig, store
from .errors import FarmError

PUSH_FAILED = 3
# Commit-message lines that record what a commit did, so it can be redone on top of
# a remote that moved on (see replay_local). Base64 because git tidies whitespace.
EXEC_RECORD = "Farm-Exec: "
MIGRATE_RECORD = "Farm-Migrate: "
MAX_ROWS = 500
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
    if db.dump(conn) != text:
        raise FarmError("refusing to save: the text does not reload to an identical database")


def worktree_problems(root):
    """Problems with the data as it is on disk now (used after a rebase)."""
    try:
        conn = db.load(store.read_sql(root))
    except FarmError as e:
        return [str(e)]
    return db.check(conn) + mig.problems(conn, store.read_migrations(root))


def push_with_sync(root):
    return gitops.sync_push(root, lambda: worktree_problems(root),
                            lambda before: replay_local(root, before))


def _save_commit(root, old_text, new_text, extra_paths, message=None, reuse=None):
    """Write the new text and commit it; on a failed commit, put the old text back."""
    path = Path(root) / store.SQL_REL
    existed = path.exists()
    store.atomic_write(path, new_text)
    try:
        return gitops.commit(root, [store.SQL_REL, *extra_paths], message, reuse=reuse)
    except FarmError:
        if existed:
            store.atomic_write(path, old_text)
        else:
            path.unlink(missing_ok=True)
        raise


def _save_commit_push(root, old_text, new_text, extra_paths, message):
    warning = gitops.ensure_hooks(root)
    if warning:
        print(warning, file=sys.stderr)
    sha = _save_commit(root, old_text, new_text, extra_paths, message)
    print(f"saved and committed {sha[:10]}")
    ok, output = push_with_sync(root)
    if not ok:
        print(f"warning: committed locally but git push failed:\n{output}", file=sys.stderr)
        return PUSH_FAILED
    if output:
        print(output)
    print("pushed")
    return 0


def _exec_change(root, sql):
    """(old text, new text) after running a data write; new text is None if nothing changed."""
    text, files = store.read_sql(root), store.read_migrations(root)
    conn = db.load(text)
    found = db.check(conn) + mig.problems(conn, files)
    if found:
        raise FarmError("the saved database has problems; fix them first: " + "; ".join(found))
    waiting = mig.pending(conn, files)
    if waiting:
        raise FarmError("apply pending migrations first (bin/farm migrate): " + ", ".join(waiting))
    db.execute_write(conn, sql)
    new_text = db.dump(conn)
    if new_text == text:
        return text, None
    _verify(new_text, files)
    return text, new_text


def _migrate_change(root):
    """(old text, new text, names applied); names is empty if nothing was pending."""
    text, files = store.read_sql(root), store.read_migrations(root)
    conn = db.load(text)
    found = db.check(conn)
    if found:
        raise FarmError("the saved database has problems; fix them first: " + "; ".join(found))
    applied = mig.apply_pending(conn, files, _now())
    if not applied:
        return text, None, []
    new_text = db.dump(conn)
    _verify(new_text, files)
    return text, new_text, applied


def _replay_record(message, paths, parents):
    """('exec', sql) or ('migrate', [names]) for a commit made by this tool, else None."""
    if parents != 1:
        return None
    for line in message.splitlines():
        if line.startswith(EXEC_RECORD) and paths == [store.SQL_REL]:
            try:
                return "exec", base64.b64decode(line[len(EXEC_RECORD):], validate=True).decode()
            except (binascii.Error, UnicodeDecodeError):
                return None
        if line.startswith(MIGRATE_RECORD):
            names = line[len(MIGRATE_RECORD):].split()
            expected = [store.SQL_REL] + [f"{store.MIGRATIONS_REL}/{n}" for n in names]
            if names and sorted(paths) == sorted(expected):
                return "migrate", names
    return None


def replay_local(root, before):
    """Redo the local commits (up to `before`) on top of the fetched upstream by re-running
    the SQL or migrations each one recorded. All or nothing: on any failure HEAD goes
    back to `before`. Returns (ok, message). The caller holds the farm lock."""
    records = []
    for sha in gitops.local_commits(root, before):
        record = _replay_record(*gitops.commit_info(root, sha))
        if record is None:
            return False, (f"commit {sha[:10]} was not made by bin/farm exec or migrate, so "
                           "it is not redone automatically; resolve by hand (git pull --rebase)")
        records.append((sha, record))
    try:
        gitops.reset_hard(root, "@{upstream}")
        for sha, (kind, payload) in records:
            if kind == "exec":
                text, new_text = _exec_change(root, payload)
                if new_text is not None:
                    _save_commit(root, text, new_text, [], reuse=sha)
                continue
            rels = [f"{store.MIGRATIONS_REL}/{n}" for n in payload]
            gitops.checkout_paths(root, sha, rels)
            text, new_text, applied = _migrate_change(root)
            if sorted(applied) != sorted(payload):
                raise FarmError(f"replaying {sha[:10]} would apply {applied or 'nothing'} "
                                f"instead of {payload}")
            _save_commit(root, text, new_text, rels, reuse=sha)
    except FarmError as e:
        gitops.reset_hard(root, before)
        return False, str(e)
    return True, (f"replayed {len(records)} local change(s) on top of the newer remote data")


def cmd_exec(root, args):
    message = args.message.strip()
    if not message:
        raise FarmError("a commit message (-m) is required")
    sql = _sql_arg(args.sql)
    with store.lock(gitops.lock_path(root)):
        _refuse_if_edited_outside(root)
        text, new_text = _exec_change(root, sql)
        if new_text is None:
            print("no changes; nothing committed")
            return 0
        record = base64.b64encode(sql.encode("utf-8")).decode("ascii")
        return _save_commit_push(root, text, new_text, [],
                                 f"{message}\n\n{EXEC_RECORD}{record}")


def cmd_migrate(root, args):
    with store.lock(gitops.lock_path(root)):
        _refuse_if_edited_outside(root)
        text, new_text, applied = _migrate_change(root)
        if not applied:
            print("nothing to apply")
            return 0
        message = (args.message or "").strip() or "Apply migration " + ", ".join(applied)
        print("applied: " + ", ".join(applied))
        return _save_commit_push(root, text, new_text,
                                 [f"{store.MIGRATIONS_REL}/{n}" for n in applied],
                                 f"{message}\n\n{MIGRATE_RECORD}{' '.join(applied)}")


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
    shown = rows if args.all else rows[:MAX_ROWS]
    for row in shown:
        out.writerow(["" if v is None else v.hex() if isinstance(v, bytes) else v for v in row])
    if len(shown) < len(rows):
        print(f"note: showing {len(shown)} of {len(rows)} rows; narrow the query (WHERE, "
              "LIMIT, GROUP BY) or pass --all", file=sys.stderr)
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
    deleted = args.staged and gitops.show_staged(root, store.SQL_REL) is None \
        and gitops.head_has(root, store.SQL_REL)
    try:
        conn = db.load(text)
    except FarmError as e:
        found = [str(e)]
    else:
        found = db.check(conn) + mig.problems(conn, files)
        if deleted:
            found.insert(0, f"{store.SQL_REL} would be deleted; farm data must never be removed")
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
    q.add_argument("--all", action="store_true", help=f"print all rows (default: first {MAX_ROWS})")
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
