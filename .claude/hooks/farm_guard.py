#!/usr/bin/env python3
"""PreToolUse hook: block changes to data/farm.sql that bypass bin/farm (exit 2 = block)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
PROTECTED = ("farm.sql", "farm.db")


def main():
    raw = sys.stdin.read()
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from farmdb import hooks
        code, message = hooks.guard(json.loads(raw), str(ROOT))
    except Exception as e:
        # Fail closed only where the farm data is involved, so a guard bug can
        # never lock out every tool (including the ones needed to fix it).
        if any(p in raw.lower() for p in PROTECTED):
            print(f"farm guard error, blocking to be safe: {e!r}", file=sys.stderr)
            return 2
        return 0
    if message:
        print(message, file=sys.stderr)
    return code


sys.exit(main())
