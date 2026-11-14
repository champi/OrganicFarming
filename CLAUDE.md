# Farm records database

Farm data lives in `data/farm.sql`: a SQLite database stored as a text dump. **Only `bin/farm` may change it.** Hooks in `.claude/` block other writes, and the git pre-commit check rejects broken data.

| Task | Command |
|---|---|
| Ask a question | `bin/farm query "SELECT ..."` (read-only, prints CSV) |
| Add, change or delete data | `bin/farm exec -m "What changed" "INSERT ...;"` (validates, commits, pushes) |
| Change the schema | write a new `data/migrations/NNN_name.sql`, then `bin/farm migrate` |
| Check everything | `bin/farm check` |

Rules:
- Answer questions with SQL through `bin/farm query`; don't read the whole dump into context.
- Log only what the user stated. Never invent values; use NULL for anything unknown.
- Dates are ISO `YYYY-MM-DD`. Quantities go in a number column, units in their own column.
- Never edit an applied migration. Write a new one with a higher number. Tables must be `STRICT` with an `INTEGER PRIMARY KEY`.
- Exit code 3 means the change was saved and committed but the push failed. Push later; nothing is lost.
- Run tests after changing `tools/farmdb`: `cd tools/tests && python3 -m unittest discover -p 'test_*.py'`.
- On a new clone, run `bin/setup` once to enable the git pre-commit check.

What the data is for: [GOALS.md](GOALS.md).
