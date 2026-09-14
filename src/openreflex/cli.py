import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .project import approval, approve, home, project_resolution, project_root, revoke

AGENT_CHOICES = ["claude-code", "codex", "cursor", "opencode"]


def _project(value: str | None) -> Path:
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
    return 0


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
    verb = "would update" if args.dry_run else "updated"
    print("OPENREFLEX / CONNECT")
    print(f"  agent       {args.agent}")
    print(f"  project     {project}")
    if changes:
        print(f"  config      {verb} {len(changes)} file{'s' if len(changes) != 1 else ''}")
        for change in changes:
            print(f"              {change}")
    else:
        print("  config      already connected")
    if not args.dry_run:
        print("  memory      enabled")
        print("  storage     local")
        print("\n  [ok] reflex active")
        if args.agent == "codex":
            print("\nCodex requires one trust step: open /hooks and approve the OpenReflex entries.")
    if shutil.which("openreflex") is None:
        print("\nWarning: `openreflex` is not on PATH; hooks will not run. Install with `uv tool install .` or `pipx install .`.")
    return 0


def cmd_uninstall(args) -> int:
    from .install import uninstall

    project = _project(args.project)
    changes = uninstall(args.agent, project, dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    print("OPENREFLEX / DISCONNECT")
    print(f"  agent       {args.agent}")
    print(f"  project     {project}")
    if changes:
        print(f"  config      {verb} OpenReflex entries from {len(changes)} file{'s' if len(changes) != 1 else ''}")
        for change in changes:
            print(f"              {change}")
    else:
        print("  config      no project integration found")
    print("  memory      preserved")
    if not args.dry_run:
        print("\n  [ok] disconnected")
        print("\nRun `openreflex forget --yes` separately if you also want to delete local experience data.")
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
    control = data["execution_control"]
    print(f"  verdicts: {control['verdicts'] or '-'}   tasks within tool-call budget: {control['tasks_within_tool_call_budget']}")
    return 0


def cmd_context(args) -> int:
    from .engine import Engine

    engine = Engine(_project(args.project))
    try:
        print(engine.preview(args.task))
    finally:
        engine.close()
    return 0


def cmd_why(args) -> int:
    from .engine import Engine

    engine = Engine(_project(args.project))
    try:
        print(engine.why())
    finally:
        engine.close()
    return 0


def cmd_trace(args) -> int:
    from .engine import Engine

    engine = Engine(_project(args.project))
    try:
        print(engine.trace())
    finally:
        engine.close()
    return 0


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _claude_plugin_enabled() -> bool:
    settings = _json(Path.home() / ".claude" / "settings.json")
    enabled = settings.get("enabledPlugins")
    if isinstance(enabled, dict):
        return any("openreflex" in str(name).lower() and value is not False for name, value in enabled.items())
    if isinstance(enabled, list):
        return any("openreflex" in str(name).lower() for name in enabled)
    return False


def _recent_hook_trace(project: Path) -> str | None:
    path = home() / "logs" / "hooks.log"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
    except OSError:
        return None
    target = str(project)
    for line in reversed(lines):
        if target in line:
            return line
    return lines[-1] if lines else None


def cmd_doctor(args) -> int:
    from .store import database_path

    project = _project(args.project)
    resolution = project_resolution(args.project)
    claude_project = "openreflex hook" in _read(project / ".claude" / "settings.json")
    claude_plugin = _claude_plugin_enabled()
    trace = _recent_hook_trace(project)
    checks = [
        ("openreflex on PATH", shutil.which("openreflex") is not None),
        ("project enabled", approval(project) is not None),
        ("database exists", database_path(project).exists()),
        ("Claude Code integration", claude_project or claude_plugin),
        ("Codex hooks (project)", "openreflex hook" in _read(project / ".codex" / "hooks.json")),
        ("Cursor hooks (project)", "openreflex hook" in _read(project / ".cursor" / "hooks.json")),
        ("OpenCode plugin (project)", (project / ".opencode" / "plugins" / "openreflex.ts").exists()),
        ("hook activity observed", trace is not None),
    ]
    print("OPENREFLEX / DOCTOR")
    print(f"  project     {project}")
    print(f"  resolution  {resolution['source']}")
    if resolution.get("cwd"):
        print(f"  hook cwd    {resolution['cwd']}")
    if resolution.get("agent_hint"):
        print(f"  agent hint  {resolution['agent_hint']}")
    print(f"  data        {database_path(project)}")
    if claude_plugin and not claude_project:
        print("  Claude      plugin/global install detected")
    for name, ok in checks:
        print(f"  [{'ok' if ok else '--'}] {name}")
    if trace:
        print(f"Last hook trace:\n  {trace}")
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
    hook.add_argument("agent", help=", ".join(AGENT_CHOICES))
    hook.add_argument("event", nargs="?")
    hook.set_defaults(func=cmd_hook)

    mcp = sub.add_parser("mcp", help="Run the MCP stdio server")
    mcp.add_argument("--project")
    mcp.set_defaults(func=cmd_mcp)

    for name, func, text in (("approve", cmd_approve, "Enable capture for a project"),
                             ("revoke", cmd_revoke, "Disable capture for a project"),
                             ("doctor", cmd_doctor, "Check installation, project resolution, and recent hook activity"),
                             ("why", cmd_why, "Explain the latest OpenReflex execution decision"),
                             ("trace", cmd_trace, "Show the latest execution decision timeline")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--project")
        command.set_defaults(func=func)

    for name, func, text in (("install", cmd_install, "Connect OpenReflex hooks + MCP for an agent"),
                             ("uninstall", cmd_uninstall, "Disconnect OpenReflex hooks + MCP while preserving memory")):
        command = sub.add_parser(name, help=text)
        command.add_argument("agent", choices=AGENT_CHOICES)
        command.add_argument("--project")
        command.add_argument("--dry-run", action="store_true")
        command.set_defaults(func=func)

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
        try:
            return cmd_hook(argparse.Namespace(agent=argv[1] if len(argv) > 1 else "", event=argv[2] if len(argv) > 2 else ""))
        except BaseException:  # noqa: BLE001
            return 0
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
