#!/usr/bin/env python3
"""Stop hook: don't end a turn with farm data uncommitted or broken; push pending commits."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        sys.path.insert(0, str(ROOT / "tools"))
        from farmdb import hooks
        result = hooks.stop(event, str(ROOT))
    except Exception as e:  # never trap the session
        print(json.dumps({"systemMessage": f"farm stop hook failed: {e!r}"}))
        return 0
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.code


sys.exit(main())
