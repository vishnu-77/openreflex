import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .project import approval, approve, home, project_root, revoke

AGENT_CHOICES = ["claude-code", "codex", "cursor", "opencode"]


def _project(value: str | None) -> Path:
    # An unexpanded ${VAR} placeholder from an agent config means "not provided".
    return project_root(None if not value or "${" in value else value)


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_hook(args) -> int:
    from .hooks import safe_handle

    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    output = safe_handle(args.agent, args.event or "", raw)
    if output:
        sys.stdout.write(output)
        sys.stdout.flush()
    return 0  # never block the agent


def cmd_mcp(args) -> int:
    from .mcp_server import serve

    serve(None if not args.project or "${" in args.project else args.project)
    return 0


def cmd_approve(args) -> int:
    project = _project(args.project)
    record = approve(project)
    print(f"OpenReflex enabled for {project} (since {time.strftime('%Y-%m-%d %H:%M', time.localtime(record['approved_at']))}).")
    return 0


def cmd_revoke(args) -> int:
    project = _project(args.project)
    print(f"Capture disabled for {project}." if revoke(project) else f"{project} was not enabled.")
    return 0


def cmd_install(args) -> int:
    from .install import install

    project = _project(args.project)
    changes = install(args.agent, project, dry_run=args.dry_run)
    verb = "Would write" if args.dry_run else "Wrote"
    for change in changes:
        print(f"{verb} {change}")
    if not changes:
        print("Already installed; nothing to change.")
    if not args.dry_run:
        print(f"Enabled for {project}.")
        if args.agent == "codex":
            print("Codex asks you to trust new hooks once: open /hooks in Codex and approve the OpenReflex entries.")
    if shutil.which("openreflex") is None:
        print("Warning: `openreflex` is not on PATH; hooks will not run. Install with `uv tool install .` or `pipx install .`.")
    return 0


def cmd_status(args) -> int:
    from .engine import Engine
    from .metrics import project_metrics

    project = _project(args.project)
    record = approval(project)
    engine = Engine(project)
    try:
        data = project_metrics(engine, record)
    finally:
        engine.close()
    data["enabled"] = record is not None
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    reuse, regret, routing = data["experience_reuse"], data["execution_regret"], data["routing"]
    eff = data["efficiency_observational"]
    print(f"OpenReflex {__version__} - {project}")
    print(f"  enabled: {data['enabled']}   agents: {', '.join(data['engagement']['agents']) or '-'}")
    print(f"  tasks: {data['engagement']['tasks']}   experiences: {data['engagement']['experiences']}   lessons: {data['lessons']}")
    print(f"  first session captured: {data['activation']['first_session_captured']}   "
          f"seconds to first task: {data['activation']['seconds_to_first_task']}")
    print(f"  tasks that used prior experience: {reuse['benefit_rate']}")
    print(f"  success rate (known outcomes): {data['outcomes']['success_rate']}   verified: {data['outcomes']['verified']}")
    print(f"  tool calls with vs without prior experience: {eff['with_prior_experience']['tool_calls']} vs "
          f"{eff['without_prior_experience']['tool_calls']} (observational)")
    print(f"  mean execution regret: {regret['mean']}   routing agreement: {routing['agreement']}")
    print(f"  live alerts: {data['live_alerts'] or '-'}")
    return 0


def cmd_context(args) -> int:
    from .engine import Engine

    engine = Engine(_project(args.project))
    try:
        print(engine.preview(args.task))
    finally:
        engine.close()
    return 0


def cmd_doctor(args) -> int:
    from .store import database_path

    project = _project(args.project)
    checks = [
        ("openreflex on PATH", shutil.which("openreflex") is not None),
        ("project enabled", approval(project) is not None),
        ("database exists", database_path(project).exists()),
        ("Claude Code hooks (project)", "openreflex hook" in _read(project / ".claude" / "settings.json")),
        ("Codex hooks (project)", "openreflex hook" in _read(project / ".codex" / "hooks.json")),
        ("Cursor hooks (project)", "openreflex hook" in _read(project / ".cursor" / "hooks.json")),
        ("OpenCode plugin (project)", (project / ".opencode" / "plugins" / "openreflex.ts").exists()),
    ]
    print(f"Project: {project}\nData:    {database_path(project)}")
    for name, ok in checks:
        print(f"  [{'ok' if ok else '--'}] {name}")
    log = home() / "logs" / "errors.log"
    if log.exists():
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        print("Recent hook errors:\n  " + "\n  ".join(tail))
    return 0


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def cmd_forget(args) -> int:
    from .store import database_path

    project = _project(args.project)
    directory = database_path(project).parent
    if not args.yes:
        print(f"This deletes all OpenReflex data for {project} ({directory}). Re-run with --yes to confirm.")
        return 1
    shutil.rmtree(directory, ignore_errors=True)
    print(f"Deleted {directory}.")
    return 0


def cmd_benchmark(args) -> int:
    from .benchmark import format_report, run_benchmark

    report = run_benchmark(episodes=args.episodes, seeds=args.seeds)
    print(format_report(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openreflex", description="Ambient execution intelligence for coding agents.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser("hook", help="Handle a lifecycle hook (JSON on stdin); used by agent configs")
    # No `choices`: argparse exits 2 on bad input, and exit code 2 means "block" to Claude Code and Codex.
    hook.add_argument("agent", help=", ".join(AGENT_CHOICES))
    hook.add_argument("event", nargs="?")
    hook.set_defaults(func=cmd_hook)

    mcp = sub.add_parser("mcp", help="Run the MCP stdio server")
    mcp.add_argument("--project")
    mcp.set_defaults(func=cmd_mcp)

    for name, func, text in (("approve", cmd_approve, "Enable capture for a project"),
                             ("revoke", cmd_revoke, "Disable capture for a project"),
                             ("doctor", cmd_doctor, "Check installation and recent hook errors")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--project")
        command.set_defaults(func=func)

    install = sub.add_parser("install", help="Write project hook + MCP config for an agent and enable the project")
    install.add_argument("agent", choices=AGENT_CHOICES)
    install.add_argument("--project")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)

    status = sub.add_parser("status", help="Show capture, reuse, regret, and routing metrics")
    status.add_argument("--project")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    context = sub.add_parser("context", help="Preview the Execution Context for a task description")
    context.add_argument("task")
    context.add_argument("--project")
    context.set_defaults(func=cmd_context)

    forget = sub.add_parser("forget", help="Delete all captured data for a project")
    forget.add_argument("--project")
    forget.add_argument("--yes", action="store_true")
    forget.set_defaults(func=cmd_forget)

    bench = sub.add_parser("benchmark", help="Run the simulated baseline-vs-guided benchmark suite")
    bench.add_argument("--episodes", type=int, default=150)
    bench.add_argument("--seeds", type=int, default=3)
    bench.add_argument("--out", default="benchmark-results.json")
    bench.set_defaults(func=cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:
        # Hook invocations must never fail loudly or return a blocking exit code, whatever the arguments.
        try:
            return cmd_hook(argparse.Namespace(agent=argv[1] if len(argv) > 1 else "", event=argv[2] if len(argv) > 2 else ""))
        except BaseException:  # noqa: BLE001
            return 0
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
