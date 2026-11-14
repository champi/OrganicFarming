"""The few git operations the tool needs. All take the repo root explicitly."""
import os
import subprocess
from pathlib import Path

from .errors import FarmError


def run(root, *args, timeout=120, env=None):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          timeout=timeout, env=env)


def _network_env():
    """Never wait for a password prompt or a dead connection (hooks have no terminal)."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=20")
    return env


def _network(root, *args):
    try:
        r = run(root, *args, timeout=45, env=_network_env())
    except subprocess.TimeoutExpired:
        return False, f"git {args[0]} timed out"
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def ensure_hooks(root):
    """Turn on the versioned pre-commit check if this clone never ran bin/setup.
    Returns a warning if hooks point somewhere else (left untouched)."""
    current = run(root, "config", "--get", "core.hooksPath").stdout.strip()
    if current == ".githooks":
        return None
    if not current:
        if (Path(root) / ".githooks" / "pre-commit").exists():
            run(root, "config", "core.hooksPath", ".githooks")
        return None
    return (f"warning: git core.hooksPath is {current!r}, so the farm pre-commit check "
            "in .githooks is not active (run bin/setup to enable it)")


def is_dirty(root, rel):
    """True if rel differs from HEAD in the index or working tree (or is untracked)."""
    r = run(root, "status", "--porcelain", "--", rel)
    if r.returncode != 0:
        raise FarmError(f"git status failed: {r.stderr.strip()}")
    return bool(r.stdout.strip())


def commit(root, rels, message):
    """Commit exactly these paths (other staged changes are left alone). Returns the sha."""
    r = run(root, "add", "--", *rels)
    if r.returncode != 0:
        raise FarmError(f"git add failed: {r.stderr.strip()}")
    r = run(root, "commit", "-q", "-m", message, "--", *rels)
    if r.returncode != 0:
        run(root, "reset", "-q", "--", *rels)  # don't leave the refused content staged
        raise FarmError(f"git commit failed:\n{(r.stdout + r.stderr).strip()}")
    return run(root, "rev-parse", "HEAD").stdout.strip()


def push(root):
    return _network(root, "push", "-q")


def _rejected_because_behind(output):
    return any(s in output for s in ("non-fast-forward", "fetch first", "[rejected]"))


def tracked_changes(root):
    return run(root, "status", "--porcelain", "--untracked-files=no").stdout.strip()


def sync_push(root, validate):
    """Push; if the remote moved on, rebase onto it when that is safe, re-validate the
    result with validate() -> list of problems, and push again. On any doubt, leave the
    local commits exactly as they were and report. Returns (ok, message)."""
    ok, output = push(root)
    if ok or not _rejected_because_behind(output):
        return ok, output
    if tracked_changes(root):
        return False, (output + "\nNot rebasing onto the remote automatically because other "
                       "tracked files have uncommitted changes. Commit them, then: git pull "
                       "--rebase && git push")
    before = run(root, "rev-parse", "HEAD").stdout.strip()
    ok, pulled = _network(root, "pull", "--rebase", "--no-autostash", "-q")
    if not ok:
        run(root, "rebase", "--abort")
        run(root, "reset", "-q", "--hard", before)
        return False, ("The remote has changes that conflict with the local farm data commit; "
                       f"nothing was merged. Resolve by hand (git pull --rebase).\n{pulled}")
    problems = validate()
    if problems:
        run(root, "reset", "-q", "--hard", before)
        return False, ("Rebasing onto the remote produced data that fails the check, so it was "
                       "undone and nothing was pushed: " + "; ".join(problems))
    return push(root)


def show_staged(root, rel):
    """Content of rel in the index, or None if it is not staged/tracked."""
    r = run(root, "show", f":{rel}")
    return r.stdout if r.returncode == 0 else None


def list_staged(root, folder_rel):
    r = run(root, "ls-files", "--", folder_rel)
    if r.returncode != 0:
        raise FarmError(f"git ls-files failed: {r.stderr.strip()}")
    return [line for line in r.stdout.splitlines() if line]


def lock_path(root):
    """Lock file inside .git, so it is never tracked or shown as untracked."""
    r = run(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if r.returncode != 0:
        raise FarmError(f"not a git repository: {root}")
    return Path(r.stdout.strip()) / "farm.lock"


def unpushed(root):
    """True if HEAD has commits its upstream lacks (False if there is no upstream)."""
    r = run(root, "rev-list", "--count", "@{upstream}..HEAD")
    return r.returncode == 0 and int(r.stdout.strip() or 0) > 0


def head_has(root, rel):
    return run(root, "cat-file", "-e", f"HEAD:{rel}").returncode == 0
