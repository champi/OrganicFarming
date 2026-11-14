"""Claude Code hooks: the PreToolUse guard and the Stop check, unit and end-to-end."""
import json
import subprocess
import sys
import unittest

from helpers import TempRepo, git
from farmdb import hooks

SCHEMA = "CREATE TABLE bed (id INTEGER PRIMARY KEY, name TEXT NOT NULL) STRICT;\n"


class BashGuard(unittest.TestCase):
    def decide(self, command, root="/repo", cwd="/repo"):
        return hooks.guard({"tool_name": "Bash", "tool_input": {"command": command},
                            "cwd": cwd}, root)

    def assertAllowed(self, command):
        code, msg = self.decide(command)
        self.assertEqual(code, 0, f"should allow: {command!r} ({msg})")

    def assertBlocked(self, command):
        code, msg = self.decide(command)
        self.assertEqual(code, 2, f"should block: {command!r}")
        self.assertIn("bin/farm", msg)

    def test_allows_commands_not_touching_the_data(self):
        for c in ["ls -la", "git status", "git commit -m 'notes'", "python3 script.py",
                  "echo farm > notes.txt", "cat README.md", "rm -rf build/"]:
            self.assertAllowed(c)

    def test_allows_the_tool_itself(self):
        for c in ["bin/farm exec -m 'Add bed' \"INSERT INTO bed VALUES (1,'A')\"",
                  "./bin/farm check", "/repo/bin/farm query 'SELECT 1'",
                  "python3 bin/farm migrate", "bin/farm check && git log -1 -- data/farm.sql",
                  "FOO=1 bin/farm check data/farm.sql"]:
            self.assertAllowed(c)

    def test_allows_reading_the_data(self):
        for c in ["cat data/farm.sql", "grep -n bed data/farm.sql", "head -50 data/farm.sql",
                  "wc -l data/farm.sql", "git diff data/farm.sql", "git log -p -- data/farm.sql",
                  "git show HEAD:data/farm.sql", "git show HEAD:data/farm.sql > /tmp/old.sql",
                  "cd data && cat farm.sql", "git status --porcelain data/farm.sql",
                  "diff data/farm.sql /tmp/x.sql", "git blame data/farm.sql"]:
            self.assertAllowed(c)

    def test_allows_undoing_local_edits(self):
        for c in ["git restore data/farm.sql", "git restore --staged --worktree data/farm.sql",
                  "git checkout -- data/farm.sql"]:
            self.assertAllowed(c)

    def test_blocks_direct_writes(self):
        for c in ["echo x >> data/farm.sql", "cat new.sql > data/farm.sql",
                  "printf 'x' >| data/farm.sql", "sed -i 's/a/b/' data/farm.sql",
                  "cp /tmp/x.sql data/farm.sql", "mv /tmp/x.sql data/farm.sql",
                  "rm data/farm.sql", "truncate -s0 data/farm.sql",
                  "tee data/farm.sql < x", "sqlite3 data/farm.db",
                  "python3 -c \"open('data/farm.sql','w').write('')\"",
                  "python3 - <<'EOF'\nopen('data/farm.sql','w')\nEOF",
                  "perl -pi -e 's/a/b/' data/farm.sql", "dd of=data/farm.sql",
                  "cd data && echo x >> farm.sql", "ls; echo x > data/farm.sql",
                  "git checkout HEAD~3 -- data/farm.sql",
                  "git restore --source=HEAD~2 data/farm.sql",
                  "git add data/farm.sql", "sort -o data/farm.sql data/farm.sql",
                  "grep x data/farm.sql > data/farm.sql",
                  "cat README.md\nrm data/farm.sql",
                  "ls\ncp /tmp/x data/farm.sql"]:
            self.assertBlocked(c)

    def test_unparseable_command_touching_data_is_blocked(self):
        self.assertBlocked("echo 'unterminated > data/farm.sql")

    def test_unparseable_command_not_touching_data_is_allowed(self):
        self.assertAllowed("echo 'unterminated")


class FileToolGuard(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        self.root = str(self.repo.root)

    def decide(self, tool, path, cwd=None):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        return hooks.guard({"tool_name": tool, "tool_input": {key: path},
                            "cwd": cwd or self.root}, self.root)

    def test_blocks_editing_the_data_file(self):
        for tool in ["Edit", "Write", "MultiEdit", "NotebookEdit"]:
            for path in [f"{self.root}/data/farm.sql", "data/farm.sql",
                         f"{self.root}/data/../data/farm.sql"]:
                with self.subTest(tool=tool, path=path):
                    code, msg = self.decide(tool, path)
                    self.assertEqual(code, 2)
                    self.assertIn("bin/farm", msg)

    def test_relative_path_resolved_from_cwd(self):
        code, _ = self.decide("Edit", "farm.sql", cwd=f"{self.root}/data")
        self.assertEqual(code, 2)

    def test_allows_other_files(self):
        for path in [f"{self.root}/README.md", f"{self.root}/data/migrations/002_new.sql",
                     f"{self.root}/data/farm.sql.bak", "/tmp/farm.sql"]:
            with self.subTest(path=path):
                self.assertEqual(self.decide("Write", path)[0], 0)

    def test_blocks_editing_an_applied_migration(self):
        self.repo.add_migration("001_init.sql", SCHEMA)
        self.assertEqual(self.repo.farm("migrate").returncode, 0)
        code, msg = self.decide("Edit", f"{self.root}/data/migrations/001_init.sql")
        self.assertEqual(code, 2)
        self.assertIn("new migration", msg)
        # an unapplied draft can still be edited
        self.assertEqual(self.decide("Write", f"{self.root}/data/migrations/002_x.sql")[0], 0)

    def test_other_tools_are_ignored(self):
        code, _ = hooks.guard({"tool_name": "Read",
                               "tool_input": {"file_path": f"{self.root}/data/farm.sql"},
                               "cwd": self.root}, self.root)
        self.assertEqual(code, 0)


class StopCheck(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)
        self.root = str(self.repo.root)

    def stop(self, active=False):
        return hooks.stop({"hook_event_name": "Stop", "stop_hook_active": active}, self.root)

    def migrate(self):
        self.repo.add_migration("001_init.sql", SCHEMA)
        self.assertEqual(self.repo.farm("migrate").returncode, 0)

    def test_repo_without_farm_data_passes(self):
        self.assertEqual(self.stop().code, 0)

    def test_clean_state_passes(self):
        self.migrate()
        self.assertEqual(self.stop().code, 0)

    def test_data_edited_outside_the_tool_blocks(self):
        self.migrate()
        self.repo.sql_path.write_text(self.repo.sql_path.read_text() + "-- x\n")
        result = self.stop()
        self.assertEqual(result.code, 2)
        self.assertIn("git restore", result.stderr)

    def test_broken_committed_data_blocks(self):
        self.migrate()
        self.repo.sql_path.write_text(self.repo.sql_path.read_text().replace(
            "COMMIT;", "INSERT INTO \"bed\" VALUES(1,NULL);\nCOMMIT;"))
        git(self.repo.root, "commit", "-q", "--no-verify", "-am", "broken")
        result = self.stop()
        self.assertEqual(result.code, 2)

    def test_does_not_block_twice_in_a_row(self):
        # stop_hook_active means we already blocked once; avoid an endless loop.
        self.migrate()
        self.repo.sql_path.write_text(self.repo.sql_path.read_text() + "-- x\n")
        result = self.stop(active=True)
        self.assertEqual(result.code, 0)
        self.assertIn("farm.sql", result.stdout)  # still surfaced to the user

    def test_unpushed_commits_are_pushed(self):
        self.migrate()
        git(self.repo.root, "remote", "set-url", "origin", str(self.repo.tmp / "nowhere.git"))
        self.assertEqual(self.repo.farm("exec", "-m", "A",
                                        "INSERT INTO bed VALUES (1,'A');").returncode, 3)
        git(self.repo.root, "remote", "set-url", "origin", str(self.repo.remote))
        result = self.stop()
        self.assertEqual(result.code, 0)
        self.assertEqual(self.repo.remote_head(), self.repo.local_head())

    def test_push_failure_warns_but_does_not_block(self):
        self.migrate()
        git(self.repo.root, "remote", "set-url", "origin", str(self.repo.tmp / "nowhere.git"))
        self.repo.farm("exec", "-m", "A", "INSERT INTO bed VALUES (1,'A');")
        result = self.stop()
        self.assertEqual(result.code, 0)
        self.assertIn("push", json.loads(result.stdout)["systemMessage"].lower())

    def test_pending_migration_is_mentioned_not_blocking(self):
        self.migrate()
        self.repo.add_migration("002_more.sql", "CREATE TABLE m (id INTEGER PRIMARY KEY) STRICT;")
        result = self.stop()
        self.assertEqual(result.code, 0)
        self.assertIn("002_more.sql", json.loads(result.stdout)["systemMessage"])


class HookScripts(unittest.TestCase):
    """The actual scripts Claude Code runs, fed JSON on stdin."""

    def setUp(self):
        self.repo = TempRepo()
        self.addCleanup(self.repo.cleanup)

    def run_hook(self, name, payload):
        return subprocess.run([sys.executable, str(self.repo.root / ".claude" / "hooks" / name)],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=self.repo.root,
                              env={"CLAUDE_PROJECT_DIR": str(self.repo.root),
                                   "PATH": "/usr/bin:/bin", "HOME": str(self.repo.tmp)})

    def test_guard_blocks_with_exit_2_and_explains_on_stderr(self):
        r = self.run_hook("farm_guard.py", {"tool_name": "Bash", "cwd": str(self.repo.root),
                                            "tool_input": {"command": "echo x >> data/farm.sql"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("bin/farm", r.stderr)

    def test_guard_allows_with_exit_0(self):
        r = self.run_hook("farm_guard.py", {"tool_name": "Bash", "cwd": str(self.repo.root),
                                            "tool_input": {"command": "ls"}})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_guard_fails_closed_on_garbage_input_mentioning_the_data(self):
        r = subprocess.run([sys.executable, str(self.repo.root / ".claude/hooks/farm_guard.py")],
                           input="not json data/farm.sql", capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_guard_failure_never_locks_out_unrelated_tools(self):
        # A guard bug must not block every command (that would also block fixing it).
        r = subprocess.run([sys.executable, str(self.repo.root / ".claude/hooks/farm_guard.py")],
                           input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_stop_script_runs(self):
        r = self.run_hook("farm_stop.py", {"hook_event_name": "Stop", "stop_hook_active": False})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_settings_file_wires_both_hooks(self):
        from helpers import REPO
        settings = json.loads((REPO / ".claude" / "settings.json").read_text())
        pre = settings["hooks"]["PreToolUse"]
        commands = [h["command"] for m in pre for h in m["hooks"]]
        self.assertTrue(any("farm_guard.py" in c for c in commands))
        matchers = "|".join(m.get("matcher", "") for m in pre)
        for tool in ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]:
            self.assertIn(tool, matchers.split("|"))
        guard = next(h for m in pre for h in m["hooks"] if "farm_guard.py" in h["command"])
        self.assertEqual(guard.get("onFailure"), "block")
        stop_cmds = [h["command"] for m in settings["hooks"]["Stop"] for h in m["hooks"]]
        self.assertTrue(any("farm_stop.py" in c for c in stop_cmds))


if __name__ == "__main__":
    unittest.main()
