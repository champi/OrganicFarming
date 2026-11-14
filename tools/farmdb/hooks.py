"""Logic for the Claude Code hooks (.claude/hooks/*.py), kept here so it is unit-tested.

guard(): PreToolUse. Blocks any tool call that would change data/farm.sql (or a farm.db)
         other than through bin/farm, and edits to already-applied migrations.
stop():  Stop. Refuses to end a turn while farm data is uncommitted or broken, and pushes
         farm commits that have not reached the remote yet.

The guard is a guardrail, not a security boundary: a determined command can hide the
path (variables, scripts). The Stop hook and the git pre-commit check are the backstops.
"""
import json
import os
import re
import shlex
from collections import namedtuple
from pathlib import Path

from . import db, gitops, migrations as mig, store
from .errors import FarmError

BLOCK = 2
PROTECTED_NAMES = ("farm.sql", "farm.db")
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_ONLY = {"cat", "head", "tail", "less", "more", "wc", "grep", "egrep", "fgrep", "rg",
             "diff", "cmp", "stat", "file", "ls", "sha256sum", "md5sum", "nl", "cut"}
GIT_READ_ONLY = {"log", "diff", "show", "status", "blame", "ls-files", "grep", "rev-list",
                 "cat-file", "shortlog"}
# These only move content between git's own committed states; whatever they produce is
# checked by the pre-commit hook and the Stop hook. (Restoring an *old* version over the
# current data, git apply, git rm etc. stay blocked.)
GIT_FROM_HISTORY = {"add", "commit", "revert", "stash"}
_ENV_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")

GUARD_MESSAGE = ("Blocked by the farm guard: data/farm.sql may only be changed through "
                 "bin/farm (exec -m MSG SQL, or migrate). Reading is fine: bin/farm query, "
                 "cat, grep, git diff/log/show.")

StopResult = namedtuple("StopResult", "code stdout stderr")


def _mentions_protected(text):
    lowered = text.lower()
    return any(name in lowered for name in PROTECTED_NAMES)


# ---------------------------------------------------------------- PreToolUse guard

def guard(event, root):
    """Return (exit_code, message). exit_code 2 blocks the tool call."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if tool == "Bash":
        return _guard_bash(tool_input.get("command") or "")
    if tool in FILE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return _guard_file(path, event.get("cwd") or root, root)
    return 0, ""


def _guard_file(path, cwd, root):
    if not path:
        return 0, ""
    target = os.path.realpath(os.path.join(cwd, path))
    data_dir = os.path.realpath(os.path.join(root, "data"))
    if target in {os.path.join(data_dir, name) for name in PROTECTED_NAMES}:
        return BLOCK, GUARD_MESSAGE
    if os.path.dirname(target) == os.path.join(data_dir, "migrations"):
        name = os.path.basename(target)
        if name in _applied_migrations(root):
            return BLOCK, (f"Blocked by the farm guard: migration {name} is already applied "
                           "and must not change. Write a new migration with a higher number.")
    return 0, ""


def _applied_migrations(root):
    try:
        return set(mig.applied(db.load(store.read_sql(root))))
    except FarmError:
        return set()


def _guard_bash(command):
    if not _mentions_protected(command):
        return 0, ""
    try:
        segments = _segments(command)
    except ValueError:
        return BLOCK, GUARD_MESSAGE + " (command could not be parsed safely)"
    for tokens in segments:
        if not _segment_allowed(tokens):
            return BLOCK, GUARD_MESSAGE
    return 0, ""


def _is_punct(token):
    return bool(token) and all(c in "();<>|&" for c in token)


def _segments(command):
    # Newlines separate commands too; shlex would treat them as plain whitespace.
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments, current = [], []
    for token in lexer:
        if _is_punct(token) and ">" not in token and "<" not in token:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _segment_allowed(tokens):
    for i, token in enumerate(tokens):
        if _is_punct(token) and ">" in token:
            if i + 1 < len(tokens) and _mentions_protected(tokens[i + 1]):
                return False
    words = [t for t in tokens if not _is_punct(t)]
    while words and _ENV_ASSIGN.fullmatch(words[0]):
        words = words[1:]
    if not any(_mentions_protected(w) for w in words):
        return True
    head = words[0]
    if _is_farm_tool(words):
        return True
    if os.path.basename(head) in READ_ONLY:
        return True
    if os.path.basename(head) == "git":
        return _git_allowed(words[1:])
    return False


def _is_farm_tool(words):
    def is_farm(word):
        return word == "bin/farm" or word.endswith("/bin/farm")
    if is_farm(words[0]):
        return True
    return os.path.basename(words[0]).startswith("python") and len(words) > 1 and is_farm(words[1])


def _git_allowed(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return False
    sub, rest = args[i], args[i + 1:]
    if sub in GIT_READ_ONLY or sub in GIT_FROM_HISTORY:
        return True
    if sub == "restore":
        return not any(a.startswith(("--source", "-s")) for a in rest)
    if sub == "checkout":
        return bool(rest) and rest[0] == "--"
    return False


# ---------------------------------------------------------------- Stop check

def stop(event, root):
    if not (Path(root) / "data").exists():
        return StopResult(0, "", "")
    try:
        # Wait for any bin/farm write in progress, so its brief "written but not yet
        # committed" moment is not mistaken for an outside edit.
        with store.lock(gitops.lock_path(root), timeout=60):
            return _stop_checks(event, root)
    except FarmError as e:
        return StopResult(0, json.dumps({"systemMessage": f"Farm data: {e}"}), "")


def _stop_checks(event, root):
    from .cli import push_with_sync
    blocks, notes = [], []
    sql_path = Path(root) / store.SQL_REL
    try:
        dirty = gitops.is_dirty(root, store.SQL_REL)
        files = store.read_migrations(root)
        if not sql_path.exists() and not dirty and not files:
            return StopResult(0, "", "")
        if dirty:
            blocks.append(f"{store.SQL_REL} has changes that did not go through bin/farm. "
                          f"Undo them (git restore --staged --worktree {store.SQL_REL}) and "
                          "redo the change with bin/farm exec.")
        try:
            conn = db.load(store.read_sql(root))
            found = db.check(conn) + mig.problems(conn, files)
            waiting = mig.pending(conn, files)
        except FarmError as e:
            found, waiting = [str(e)], []
        if found:
            blocks.append("bin/farm check found problems: " + "; ".join(found))
        if waiting:
            notes.append("migration(s) written but not applied yet: " + ", ".join(waiting))
        if not blocks and gitops.unpushed(root):
            ok, output = push_with_sync(root)
            if not ok:
                notes.append(f"farm data is committed but not pushed (git push failed: {output})")
    except Exception as e:  # never trap the session because the check itself broke
        notes.append(f"farm stop check could not run: {e!r}")
    if blocks and not event.get("stop_hook_active"):
        return StopResult(BLOCK, "", "\n".join(blocks + notes))
    messages = blocks + notes
    stdout = json.dumps({"systemMessage": "Farm data: " + " | ".join(messages)}) if messages else ""
    return StopResult(0, stdout, "")
