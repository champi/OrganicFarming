"""Shared test helpers. Importing this puts tools/ on sys.path."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import farmdb  # noqa: E402,F401

# Files that make up the system; copied into throwaway repos for black-box tests.
SYSTEM_PATHS = ["bin", "tools/farmdb", ".githooks", ".claude/hooks"]


def git(cwd, *args, check=True):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=check, env=env,
                          capture_output=True, text=True)


class TempRepo:
    """A throwaway git repo (with a bare 'origin') containing a copy of the system."""

    def __init__(self, with_remote=True):
        self.tmp = Path(tempfile.mkdtemp(prefix="farmtest-"))
        self.root = self.tmp / "repo"
        self.remote = self.tmp / "origin.git"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "master")
        for rel in SYSTEM_PATHS:
            src = REPO / rel
            if src.exists():
                shutil.copytree(src, self.root / rel,
                                ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "data" / "migrations").mkdir(parents=True)
        (self.root / "README.md").write_text("readme\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        if with_remote:
            subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(self.remote)],
                           check=True)
            git(self.root, "remote", "add", "origin", str(self.remote))
            git(self.root, "push", "-q", "-u", "origin", "master")

    @property
    def sql_path(self):
        return self.root / "data" / "farm.sql"

    def add_migration(self, name, sql):
        (self.root / "data" / "migrations" / name).write_text(sql)

    def farm(self, *args, stdin=None, env=None):
        return subprocess.run([sys.executable, str(self.root / "bin" / "farm"), *args],
                              cwd=self.root, input=stdin, capture_output=True, text=True,
                              env={**os.environ, **(env or {}),
                                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                                   "GIT_COMMITTER_NAME": "t",
                                   "GIT_COMMITTER_EMAIL": "t@example.com"})

    def head_message(self):
        """Subject line of HEAD (the body holds the machine-readable replay record)."""
        return git(self.root, "log", "-1", "--format=%s").stdout.strip()

    def head_body(self):
        return git(self.root, "log", "-1", "--format=%B").stdout

    def commit_count(self):
        return int(git(self.root, "rev-list", "--count", "HEAD").stdout)

    def remote_head(self):
        return git(self.remote, "rev-parse", "master").stdout.strip()

    def local_head(self):
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
