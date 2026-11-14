"""The few git operations the tool needs. All take the repo root explicitly."""
import subprocess

from .errors import FarmError


def run(root, *args, timeout=120):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          timeout=timeout)


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
    try:
        r = run(root, "push", "-q")
    except subprocess.TimeoutExpired:
        return False, "git push timed out"
    return r.returncode == 0, (r.stdout + r.stderr).strip()


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
    from pathlib import Path
    r = run(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if r.returncode != 0:
        raise FarmError(f"not a git repository: {root}")
    return Path(r.stdout.strip()) / "farm.lock"


def unpushed(root):
    """True if HEAD has commits its upstream lacks (False if there is no upstream)."""
    r = run(root, "rev-list", "--count", "@{upstream}..HEAD")
    return r.returncode == 0 and int(r.stdout.strip() or 0) > 0
