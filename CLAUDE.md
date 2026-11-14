# Farm records database

Farm data lives in `data/farm.sql`: a SQLite database stored as a text dump. **Only `bin/farm` may change it.** Hooks in `.claude/` block other writes, and the git pre-commit check rejects broken data.

| Task | Command |
|---|---|
| Ask a question | `bin/farm query "SELECT ..."` (read-only, prints CSV, first 500 rows unless `--all`) |
| Add, change or delete data | `bin/farm exec -m "What changed" "INSERT ...;"` (validates, commits, pushes) |
| Long SQL | `bin/farm exec -m "msg" - <<'SQL'` … `SQL` (reads stdin) |
| Change the schema | write a new `data/migrations/NNN_name.sql`, then `bin/farm migrate` |
| Undo a data change | `git revert --no-edit <sha>` (the result is checked before it can be committed) |
| Check everything | `bin/farm check` |

Rules:
- Answer questions with SQL through `bin/farm query`, using WHERE, GROUP BY and LIMIT. Don't read the whole dump into context.
- Log only what the user stated. Never invent values; use NULL for anything unknown.
- Dates are ISO `YYYY-MM-DD`; in schemas, enforce this with `CHECK (d IS date(d))`. Quantities go in a number column, units in their own column.
- Never edit an applied migration. Write a new one with a higher number. Tables must be `STRICT` with an `INTEGER PRIMARY KEY`. No virtual tables.
- Exit code 3 means the change was saved and committed but not pushed (offline, or the remote has a conflicting change). Nothing is lost: the Stop hook retries the push, and safe rebases happen automatically.
- If the guard blocks a command that only *mentions* `farm.sql` (e.g. in a commit message or heredoc), rephrase it or use the Edit/Write tools on the file you actually mean.
- After changing `tools/farmdb`, run the tests: `cd tools/tests && python3 -m unittest discover -p 'test_*.py'`. GitHub Actions also runs them on Python 3.12–3.14.

What the data is for: [GOALS.md](GOALS.md).
