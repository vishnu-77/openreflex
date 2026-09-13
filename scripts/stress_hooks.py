"""Hammer the hook CLI with parallel processes and report lost or failed writes.

    python scripts/stress_hooks.py [--workers 32] [--pairs 96]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--pairs", type=int, default=96)
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp())
    project = tmp / "repo"
    (project / ".git").mkdir(parents=True)
    env = {**os.environ, "OPENREFLEX_HOME": str(tmp / "home")}
    subprocess.run([sys.executable, "-m", "openreflex", "approve", "--project", str(project)], env=env, check=True,
                   capture_output=True)
    base = {"session_id": "stress", "cwd": str(project)}

    def hook(event, payload):
        return subprocess.run([sys.executable, "-m", "openreflex", "hook", "claude-code", event],
                              input=json.dumps(payload).encode(), capture_output=True, env=env, timeout=120).returncode

    hook("UserPromptSubmit", {**base, "prompt": "Stress the hook pipeline with parallel tool calls"})

    def pair(index):
        payload = {**base, "tool_name": "Grep", "tool_input": {"pattern": f"p{index}"}, "tool_use_id": f"t{index}"}
        return hook("PreToolUse", payload), hook("PostToolUse", {**payload, "tool_response": {"matches": index}})

    with ThreadPoolExecutor(args.workers) as pool:
        codes = list(pool.map(pair, range(args.pairs)))

    os.environ["OPENREFLEX_HOME"] = env["OPENREFLEX_HOME"]
    from openreflex.store import Store, database_path

    store = Store(database_path(project))
    calls = store.list("ToolCall", limit=100_000)
    store.close()
    statuses = {}
    for call in calls:
        statuses[call.status] = statuses.get(call.status, 0) + 1
    log = tmp / "home" / "logs" / "errors.log"
    errors = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    print(f"pairs={args.pairs} workers={args.workers} nonzero_exits={sum(c != (0, 0) for c in codes)} "
          f"stored={len(calls)} statuses={statuses} errors={len(errors)}")
    for line in errors[:5]:
        print("  ", line)
    ok = len(calls) == args.pairs and statuses.get("success") == args.pairs and not errors
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
