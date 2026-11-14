"""Black-box tests of bin/farm in throwaway git repos with a bare 'origin'."""
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

from helpers import TempRepo, git

SCHEMA = """CREATE TABLE bed (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE) STRICT;
CREATE TABLE planting (id INTEGER PRIMARY KEY,
    bed_id INTEGER NOT NULL REFERENCES bed(id),
    crop TEXT NOT NULL,
    n_plants INTEGER CHECK (n_plants > 0)) STRICT;
"""


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def migrated(self):
        self.repo.add_migration("001_init.sql", SCHEMA)
        r = self.repo.farm("migrate")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def assertOk(self, r, code=0):
        self.assertEqual(r.returncode, code, f"stdout={r.stdout!r} stderr={r.stderr!r}")

    def files_in_head(self):
        return git(self.repo.root, "show", "--name-only", "--format=", "HEAD").stdout.split()


class Migrate(RepoTest):
    def test_first_migration_creates_commits_and_pushes(self):
        self.migrated()
        self.assertTrue(self.repo.sql_path.exists())
        self.assertEqual(sorted(self.files_in_head()),
                         ["data/farm.sql", "data/migrations/001_init.sql"])
        self.assertIn("001_init.sql", self.repo.head_message())
        self.assertEqual(self.repo.remote_head(), self.repo.local_head())

    def test_nothing_pending_makes_no_commit(self):
        self.migrated()
        count = self.repo.commit_count()
        r = self.repo.farm("migrate")
        self.assertOk(r)
        self.assertIn("nothing", r.stdout.lower())
        self.assertEqual(self.repo.commit_count(), count)

    def test_failed_migration_changes_nothing(self):
        self.migrated()
        before = self.repo.sql_path.read_bytes()
        count = self.repo.commit_count()
        self.repo.add_migration("002_bad.sql", "CREATE TABLE loose (id INTEGER PRIMARY KEY);")
        r = self.repo.farm("migrate")
        self.assertOk(r, 1)
        self.assertIn("STRICT", r.stderr)
        self.assertEqual(self.repo.sql_path.read_bytes(), before)
        self.assertEqual(self.repo.commit_count(), count)

    def test_custom_message(self):
        self.repo.add_migration("001_init.sql", SCHEMA)
        self.assertOk(self.repo.farm("migrate", "-m", "Add beds and plantings"))
        self.assertTrue(self.repo.head_message().startswith("Add beds and plantings"))


class Exec(RepoTest):
    def setUp(self):
        super().setUp()
        self.migrated()

    def test_insert_is_saved_committed_and_pushed(self):
        r = self.repo.farm("exec", "-m", "Add bed A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r)
        self.assertIn("INSERT INTO \"bed\" VALUES(1,'A');", self.repo.sql_path.read_text())
        self.assertEqual(self.files_in_head(), ["data/farm.sql"])
        self.assertEqual(self.repo.head_message(), "Add bed A")
        self.assertEqual(self.repo.remote_head(), self.repo.local_head())

    def test_sql_from_stdin(self):
        r = self.repo.farm("exec", "-m", "stdin", "-", stdin="INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r)
        self.assertIn("'A'", self.repo.sql_path.read_text())

    def test_message_is_required(self):
        r = self.repo.farm("exec", "INSERT INTO bed VALUES (1, 'A');")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("'A'", self.repo.sql_path.read_text())

    def test_blank_message_is_rejected(self):
        r = self.repo.farm("exec", "-m", "  ", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 1)
        self.assertNotIn("'A'", self.repo.sql_path.read_text())

    def test_rejected_write_changes_nothing(self):
        before = self.repo.sql_path.read_bytes()
        count = self.repo.commit_count()
        r = self.repo.farm("exec", "-m", "bad", "INSERT INTO planting VALUES (1, 99, 'corn', 4);")
        self.assertOk(r, 1)
        self.assertIn("FOREIGN KEY", r.stderr.upper())
        self.assertEqual(self.repo.sql_path.read_bytes(), before)
        self.assertEqual(self.repo.commit_count(), count)

    def test_schema_change_points_to_migrations(self):
        r = self.repo.farm("exec", "-m", "x", "DROP TABLE planting;")
        self.assertOk(r, 1)
        self.assertIn("migration", r.stderr.lower())

    def test_only_the_data_file_is_committed(self):
        (self.repo.root / "README.md").write_text("edited\n")
        git(self.repo.root, "add", "README.md")
        (self.repo.root / "notes.md").write_text("untracked\n")
        self.assertOk(self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');"))
        self.assertEqual(self.files_in_head(), ["data/farm.sql"])
        status = git(self.repo.root, "status", "--porcelain").stdout
        self.assertIn("M  README.md", status)  # still staged, not committed
        self.assertIn("?? notes.md", status)

    def test_no_op_write_makes_no_commit(self):
        count = self.repo.commit_count()
        r = self.repo.farm("exec", "-m", "noop", "UPDATE bed SET name = 'Z' WHERE id = 42;")
        self.assertOk(r)
        self.assertIn("no changes", r.stdout.lower())
        self.assertEqual(self.repo.commit_count(), count)

    def test_refuses_when_data_file_was_edited_outside_the_tool(self):
        tampered = self.repo.sql_path.read_text().replace(
            "COMMIT;", "INSERT INTO \"bed\" VALUES(7,'sneaky');\nCOMMIT;")
        self.repo.sql_path.write_text(tampered)
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 1)
        self.assertIn("outside", r.stderr)
        self.assertEqual(self.repo.sql_path.read_text(), tampered)

    def test_refuses_when_committed_data_is_broken(self):
        # e.g. someone committed with --no-verify; don't build on a broken base.
        broken = self.repo.sql_path.read_text().replace(
            "COMMIT;", "INSERT INTO \"planting\" VALUES(1,99,'corn',4);\nCOMMIT;")
        self.repo.sql_path.write_text(broken)
        git(self.repo.root, "commit", "-q", "--no-verify", "-am", "broken")
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 1)
        self.assertIn("foreign key", r.stderr.lower())

    def test_refuses_while_migrations_are_pending(self):
        self.repo.add_migration("002_more.sql",
                                "CREATE TABLE more (id INTEGER PRIMARY KEY) STRICT;")
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 1)
        self.assertIn("002_more.sql", r.stderr)

    def test_push_failure_keeps_commit_and_exits_3(self):
        git(self.repo.root, "remote", "set-url", "origin", str(self.repo.tmp / "missing.git"))
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 3)
        self.assertIn("push", r.stderr.lower())
        self.assertEqual(self.repo.head_message(), "A")
        self.assertEqual(git(self.repo.root, "status", "--porcelain", "data").stdout, "")

    def test_failed_commit_restores_the_data_file(self):
        hooks_dir = self.repo.tmp / "failing-hooks"
        hooks_dir.mkdir()
        hook = hooks_dir / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'rejected by test hook' >&2\nexit 1\n")
        hook.chmod(0o755)
        git(self.repo.root, "config", "core.hooksPath", str(hooks_dir))
        before = self.repo.sql_path.read_bytes()
        count = self.repo.commit_count()
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r, 1)
        self.assertIn("rejected by test hook", r.stderr)
        self.assertEqual(self.repo.sql_path.read_bytes(), before)
        self.assertEqual(self.repo.commit_count(), count)
        self.assertEqual(git(self.repo.root, "status", "--porcelain", "--", "data").stdout, "")

    def test_failed_first_commit_removes_the_new_data_file(self):
        repo = TempRepo()
        self.addCleanup(repo.cleanup)
        hooks_dir = repo.tmp / "failing-hooks"
        hooks_dir.mkdir()
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
        (hooks_dir / "pre-commit").chmod(0o755)
        git(repo.root, "config", "core.hooksPath", str(hooks_dir))
        repo.add_migration("001_init.sql", SCHEMA)
        self.assertOk(repo.farm("migrate"), 1)
        self.assertFalse(repo.sql_path.exists())

    def test_concurrent_writers_are_serialized_and_none_are_lost(self):
        def write(i):
            return self.repo.farm("exec", "-m", f"bed {i}", f"INSERT INTO bed VALUES ({i}, 'B{i}');")
        count = self.repo.commit_count()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(write, range(1, 7)))
        for r in results:
            self.assertOk(r)
        text = self.repo.sql_path.read_text()
        for i in range(1, 7):
            self.assertIn(f"'B{i}'", text)
        self.assertEqual(self.repo.commit_count(), count + 6)
        self.assertEqual(self.repo.remote_head(), self.repo.local_head())


class RemoteAhead(RepoTest):
    """Another session or machine pushed first (this happens with forked sessions)."""

    def setUp(self):
        super().setUp()
        self.migrated()
        self.assertOk(self.repo.farm("exec", "-m", "bed", "INSERT INTO bed VALUES (1, 'A');"))
        self.other = self.repo.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(self.repo.remote), str(self.other)], check=True)

    def other_farm(self, *args):
        import os
        return subprocess.run([sys.executable, str(self.other / "bin" / "farm"), *args],
                              cwd=self.other, capture_output=True, text=True,
                              env={**os.environ, "GIT_AUTHOR_NAME": "o",
                                   "GIT_AUTHOR_EMAIL": "o@example.com", "GIT_COMMITTER_NAME": "o",
                                   "GIT_COMMITTER_EMAIL": "o@example.com"})

    def other_push_readme(self):
        (self.other / "README.md").write_text("changed elsewhere\n")
        git(self.other, "commit", "-qam", "docs elsewhere")
        git(self.other, "push", "-q")

    def rebase_in_progress(self):
        gitdir = self.repo.root / ".git"
        return (gitdir / "rebase-merge").exists() or (gitdir / "rebase-apply").exists()

    def test_unrelated_remote_commit_is_rebased_onto_and_pushed(self):
        self.other_push_readme()
        r = self.repo.farm("exec", "-m", "B", "INSERT INTO bed VALUES (2, 'B');")
        self.assertOk(r)
        self.assertEqual(self.repo.remote_head(), self.repo.local_head())
        self.assertEqual((self.repo.root / "README.md").read_text(), "changed elsewhere\n")
        self.assertIn("'B'", self.repo.sql_path.read_text())

    def test_conflicting_remote_data_is_not_merged_and_local_commit_is_kept(self):
        self.assertOk(self.other_farm("exec", "-m", "X", "INSERT INTO bed VALUES (2, 'X');"))
        r = self.repo.farm("exec", "-m", "Y", "INSERT INTO bed VALUES (2, 'Y');")
        self.assertOk(r, 3)
        self.assertFalse(self.rebase_in_progress())
        self.assertEqual(self.repo.head_message(), "Y")
        self.assertEqual(git(self.repo.root, "status", "--porcelain",
                             "--untracked-files=no").stdout, "")
        self.assertIn("'Y'", self.repo.sql_path.read_text())

    def test_clean_text_merge_that_breaks_the_data_is_undone(self):
        # Remote deletes bed 1 while we add a planting on bed 1: git merges the text
        # cleanly, but the result has a dangling foreign key.
        self.assertOk(self.other_farm("exec", "-m", "del", "DELETE FROM bed WHERE id = 1;"))
        r = self.repo.farm("exec", "-m", "plant", "INSERT INTO planting VALUES (1, 1, 'corn', 4);")
        self.assertOk(r, 3)
        self.assertIn("check", r.stderr.lower())
        self.assertEqual(self.repo.head_message(), "plant")
        self.assertFalse(self.rebase_in_progress())
        self.assertIn("'A'", self.repo.sql_path.read_text())  # our pre-rebase state is back

    def test_no_rebase_when_other_tracked_files_have_uncommitted_edits(self):
        self.other_push_readme()
        (self.repo.root / "README.md").write_text("my unsaved edit\n")
        r = self.repo.farm("exec", "-m", "B", "INSERT INTO bed VALUES (2, 'B');")
        self.assertOk(r, 3)
        self.assertEqual((self.repo.root / "README.md").read_text(), "my unsaved edit\n")
        self.assertFalse(self.rebase_in_progress())


class Hardening(RepoTest):
    def test_git_hooks_are_enabled_automatically(self):
        self.migrated()
        self.assertEqual(git(self.repo.root, "config", "core.hooksPath").stdout.strip(),
                         ".githooks")

    def test_custom_hooks_path_is_not_overridden(self):
        git(self.repo.root, "config", "core.hooksPath", "elsewhere")
        self.repo.add_migration("001_init.sql", SCHEMA)
        r = self.repo.farm("migrate")
        self.assertOk(r)
        self.assertIn("hooksPath", r.stderr)
        self.assertEqual(git(self.repo.root, "config", "core.hooksPath").stdout.strip(),
                         "elsewhere")

    def test_saved_text_must_reload_identically(self):
        from farmdb import cli
        from farmdb.errors import FarmError
        with self.assertRaises(FarmError):
            cli._verify("CREATE TABLE a (id INTEGER PRIMARY KEY) STRICT;\n", {})


class Query(RepoTest):
    def setUp(self):
        super().setUp()
        self.migrated()
        self.repo.farm("exec", "-m", "beds", "INSERT INTO bed VALUES (1, 'A'), (2, 'B,\"x\"');")

    def test_prints_csv_with_header(self):
        r = self.repo.farm("query", "SELECT id, name FROM bed ORDER BY id")
        self.assertOk(r)
        self.assertEqual(r.stdout.splitlines(), ["id,name", "1,A", '2,"B,""x"""'])

    def test_query_from_stdin(self):
        r = self.repo.farm("query", "-", stdin="SELECT count(*) AS n FROM bed;")
        self.assertOk(r)
        self.assertEqual(r.stdout.splitlines(), ["n", "2"])

    def test_writes_are_refused(self):
        before = self.repo.sql_path.read_bytes()
        count = self.repo.commit_count()
        for sql in ["DELETE FROM bed", "UPDATE bed SET name='x'", "DROP TABLE bed",
                    "INSERT INTO bed VALUES (9, 'z')"]:
            with self.subTest(sql=sql):
                r = self.repo.farm("query", sql)
                self.assertOk(r, 1)
        self.assertEqual(self.repo.sql_path.read_bytes(), before)
        self.assertEqual(self.repo.commit_count(), count)

    def test_multiple_statements_are_refused(self):
        r = self.repo.farm("query", "SELECT 1; SELECT 2;")
        self.assertOk(r, 1)

    def test_large_results_are_capped_unless_all_is_given(self):
        rows = ",".join(f"({i}, 'b{i}')" for i in range(10, 610))
        self.assertOk(self.repo.farm("exec", "-m", "many", f"INSERT INTO bed VALUES {rows};"))
        r = self.repo.farm("query", "SELECT id FROM bed")
        self.assertOk(r)
        self.assertEqual(len(r.stdout.splitlines()), 1 + 500)
        self.assertIn("--all", r.stderr)
        r = self.repo.farm("query", "--all", "SELECT id FROM bed")
        self.assertEqual(len(r.stdout.splitlines()), 1 + 602)

    def test_query_works_without_any_data_file(self):
        repo = TempRepo(with_remote=False)
        self.addCleanup(repo.cleanup)
        r = repo.farm("query", "SELECT 1 AS one")
        self.assertOk(r)
        self.assertEqual(r.stdout.splitlines(), ["one", "1"])


class Check(RepoTest):
    def setUp(self):
        super().setUp()
        self.migrated()

    def test_clean_repo_passes(self):
        self.assertOk(self.repo.farm("check"))

    def test_broken_data_fails(self):
        self.repo.sql_path.write_text(self.repo.sql_path.read_text().replace(
            "COMMIT;", "INSERT INTO \"planting\" VALUES(1,99,'corn',4);\nCOMMIT;"))
        r = self.repo.farm("check")
        self.assertOk(r, 1)
        self.assertIn("foreign key", r.stdout.lower() + r.stderr.lower())

    def test_unloadable_data_fails(self):
        self.repo.sql_path.write_text("garbage (\n")
        self.assertOk(self.repo.farm("check"), 1)

    def test_edited_applied_migration_fails(self):
        mpath = self.repo.root / "data" / "migrations" / "001_init.sql"
        mpath.write_text(mpath.read_text() + "-- edited\n")
        r = self.repo.farm("check")
        self.assertOk(r, 1)
        self.assertIn("001_init.sql", r.stdout + r.stderr)

    def test_staged_checks_the_index_not_the_working_tree(self):
        good = self.repo.sql_path.read_text()
        bad = good.replace("COMMIT;", "INSERT INTO \"planting\" VALUES(1,99,'c',4);\nCOMMIT;")
        self.repo.sql_path.write_text(bad)
        git(self.repo.root, "add", "data/farm.sql")
        self.repo.sql_path.write_text(good)          # working tree fine, index broken
        self.assertOk(self.repo.farm("check", "--staged"), 1)
        self.assertOk(self.repo.farm("check"))
        git(self.repo.root, "add", "data/farm.sql")  # now both fine
        self.assertOk(self.repo.farm("check", "--staged"))


class PreCommitHook(RepoTest):
    def setUp(self):
        super().setUp()
        r = subprocess.run([sys.executable, str(self.repo.root / "bin" / "setup")],
                           cwd=self.repo.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.migrated()

    def test_setup_points_git_at_versioned_hooks(self):
        self.assertEqual(git(self.repo.root, "config", "core.hooksPath").stdout.strip(),
                         ".githooks")

    def test_setup_is_idempotent(self):
        r = subprocess.run([sys.executable, str(self.repo.root / "bin" / "setup")],
                           cwd=self.repo.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commit_of_broken_data_is_blocked(self):
        self.repo.sql_path.write_text(self.repo.sql_path.read_text().replace(
            "COMMIT;", "INSERT INTO \"planting\" VALUES(1,99,'corn',4);\nCOMMIT;"))
        r = git(self.repo.root, "commit", "-am", "sneaky", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("foreign key", (r.stdout + r.stderr).lower())

    def test_commit_of_edited_applied_migration_is_blocked(self):
        mpath = self.repo.root / "data" / "migrations" / "001_init.sql"
        mpath.write_text(mpath.read_text() + "-- edited\n")
        r = git(self.repo.root, "commit", "-am", "edit migration", check=False)
        self.assertNotEqual(r.returncode, 0)

    def test_deleting_the_data_file_is_blocked(self):
        git(self.repo.root, "rm", "-q", "data/farm.sql")
        r = git(self.repo.root, "commit", "-m", "oops", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("deleted", (r.stdout + r.stderr).lower())

    def test_unrelated_commits_are_not_affected(self):
        (self.repo.root / "README.md").write_text("changed\n")
        r = git(self.repo.root, "commit", "-am", "docs", check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def _fake_suite(self, passing):
        tests = self.repo.root / "tools" / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "test_fake.py").write_text(
            "import os, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_git_env_is_scrubbed(self):\n"
            "        self.assertFalse([k for k in os.environ if k.startswith('GIT_')])\n"
            f"    def test_x(self):\n        self.assertTrue({passing})\n")
        git(self.repo.root, "add", "tools/tests/test_fake.py")

    def test_code_commit_is_blocked_when_tests_fail(self):
        self._fake_suite(passing=False)
        r = git(self.repo.root, "commit", "-m", "break", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tests failed", (r.stdout + r.stderr).lower())

    def test_code_commit_runs_tests_with_git_env_scrubbed_and_passes(self):
        self._fake_suite(passing=True)
        r = git(self.repo.root, "commit", "-m", "ok", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_docs_commit_does_not_run_tests(self):
        self._fake_suite(passing=False)
        git(self.repo.root, "reset", "-q")          # unstage the failing suite
        (self.repo.root / "README.md").write_text("docs\n")
        r = git(self.repo.root, "commit", "-qam", "docs", check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_tool_commits_pass_the_hook(self):
        r = self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1, 'A');")
        self.assertOk(r)


if __name__ == "__main__":
    unittest.main()
