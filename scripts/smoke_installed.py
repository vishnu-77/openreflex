"""Smoke-test an *installed* openreflex (from a wheel), independent of the source tree.

Run from outside the repo:  python scripts/smoke_installed.py
Checks: console script on PATH, bundled OpenCode plugin, hook capture round trip, status, MCP over stdio.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    # Prefer the script installed alongside this interpreter (the venv under test), then PATH.
    exe = shutil.which("openreflex", path=str(Path(sys.executable).parent)) or shutil.which("openreflex")
    assert exe, "openreflex console script is not on PATH"
    import openreflex
    assert "site-packages" in openreflex.__file__, f"imported from source tree: {openreflex.__file__}"

    tmp = Path(tempfile.mkdtemp())
    project = tmp / "repo"
    (project / ".git").mkdir(parents=True)
    env = {**os.environ, "OPENREFLEX_HOME": str(tmp / "home")}
    env.pop("PYTHONPATH", None)

    def run(*args, stdin=""):
        result = subprocess.run([exe, *args], input=stdin.encode(), capture_output=True, env=env, cwd=project, timeout=120)
        assert result.returncode == 0, (args, result.stdout, result.stderr)
        return result.stdout.decode()

    print(run("--version").strip())
    run("install", "opencode", "--project", str(project))
    assert (project / ".opencode" / "plugins" / "openreflex.ts").read_text(encoding="utf-8").startswith("// OpenReflex")

    base = {"session_id": "smoke", "cwd": str(project)}
    edit = {**base, "tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}, "tool_use_id": "1"}
    test = {**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "2"}
    for event, payload in [("UserPromptSubmit", {**base, "prompt": "Fix the date parsing bug in the importer"}),
                           ("PreToolUse", edit), ("PostToolUse", {**edit, "tool_response": {}}),
                           ("PreToolUse", test), ("PostToolUse", {**test, "tool_response": {"stdout": "1 passed"}}),
                           ("Stop", base)]:
        run("hook", "claude-code", event, stdin=json.dumps(payload))
    status = json.loads(run("status", "--json", "--project", str(project)))
    assert status["engagement"]["experiences"] == 1 and status["outcomes"]["success_rate"] == 1.0, status
    assert "src/app.py" in run("context", "Fix date parsing in the importer", "--project", str(project))

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def mcp_check():
        params = StdioServerParameters(command=exe, args=["mcp", "--project", str(project)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {"get_execution_context", "record_outcome", "search_experience"} <= names, names
                result = await session.call_tool("search_experience", {"query": "date parsing importer"})
                assert "src/app.py" in result.content[0].text

    asyncio.run(mcp_check())
    print("smoke ok:", sys.platform, sys.version.split()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
