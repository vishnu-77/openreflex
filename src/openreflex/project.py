"""Project identity, per-project approval, and local logging. Nothing is captured for unapproved projects."""

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("OPENREFLEX_HOME") or Path.home() / ".openreflex")


def atomic_write_text(path: Path, text: str) -> None:
    """Replace path atomically; a per-writer temp file keeps concurrent writers from clobbering each other."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(text, encoding="utf-8")
    try:
        for attempt in range(20):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                # Windows denies a replace while another writer's replace of the same file is in flight.
                time.sleep(min(0.005 * 2**attempt, 0.1))
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _repo_root(start: Path) -> tuple[Path, str]:
    for candidate in (start, *start.parents):
        if (candidate / ".openreflex.json").exists():
            return candidate, "openreflex-marker"
        if (candidate / ".git").exists():
            return candidate, "git-root"
    return start, "directory"


def project_resolution(cwd: str | os.PathLike | None = None) -> dict[str, str | None]:
    """Resolve project identity and retain provenance for diagnostics.

    OPENREFLEX_PROJECT is authoritative. Agent project-directory variables are only
    fallbacks when the hook payload does not provide cwd.
    """
    override = os.environ.get("OPENREFLEX_PROJECT")
    agent_hint = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CURSOR_PROJECT_DIR")
    try:
        if override:
            root = Path(override).resolve()
            return {"project": str(root), "source": "OPENREFLEX_PROJECT", "cwd": str(cwd) if cwd else None,
                    "agent_hint": agent_hint}
        start = Path(cwd or agent_hint or os.getcwd()).resolve()
        root, boundary = _repo_root(start)
        if cwd:
            source = f"hook-cwd/{boundary}"
        elif agent_hint:
            source = f"agent-hint/{boundary}"
        else:
            source = f"process-cwd/{boundary}"
        return {"project": str(root), "source": source, "cwd": str(cwd) if cwd else None,
                "agent_hint": agent_hint}
    except (OSError, ValueError):
        fallback = Path(os.getcwd()).resolve()
        root, boundary = _repo_root(fallback)
        return {"project": str(root), "source": f"fallback/{boundary}", "cwd": str(cwd) if cwd else None,
                "agent_hint": agent_hint}


def project_root(cwd: str | os.PathLike | None = None, *, hook_session: str | None = None) -> Path:
    """The nearest repository root, unless OPENREFLEX_PROJECT explicitly overrides it."""
    resolution = project_resolution(cwd)
    # Only actual hook subprocesses create hook-health traces. Doctor/status must not make themselves look healthy.
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        agent = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        event = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        log_hook_resolution(agent, event, hook_session or "", resolution)
    return Path(resolution["project"])


def _key(project: Path) -> str:
    return os.path.normcase(str(project.resolve()))


def _approvals_path() -> Path:
    return home() / "approvals.json"


def _read_approvals() -> dict:
    try:
        return json.loads(_approvals_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_approvals(data: dict) -> None:
    atomic_write_text(_approvals_path(), json.dumps(data, indent=2, sort_keys=True))


def approval(project: Path) -> dict | None:
    if os.environ.get("OPENREFLEX_DISABLE") == "1":
        return None
    record = _read_approvals().get(_key(project))
    if record is None and os.environ.get("OPENREFLEX_AUTO_APPROVE") == "1":
        return approve(project, source="env")
    return record


def approve(project: Path, source: str = "cli") -> dict:
    data = _read_approvals()
    record = data.get(_key(project)) or {"path": str(project.resolve()), "approved_at": time.time(), "source": source}
    data[_key(project)] = record
    _write_approvals(data)
    return record


def revoke(project: Path) -> bool:
    data = _read_approvals()
    removed = data.pop(_key(project), None) is not None
    _write_approvals(data)
    return removed


def should_notify_unapproved(project: Path, interval: float = 86400) -> bool:
    marker = home() / "notices" / (hashlib.sha256(_key(project).encode()).hexdigest()[:24] + ".txt")
    try:
        if time.time() - marker.stat().st_mtime < interval:
            return False
    except OSError:
        pass
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(project), encoding="utf-8")
    except OSError:
        return False
    return True


def _append_log(name: str, message: str, max_bytes: int = 1_000_000) -> None:
    path = home() / "logs" / name
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
    except OSError:
        pass


def log_error(message: str) -> None:
    _append_log("errors.log", message)


def log_hook_resolution(agent: str, event: str, session: str, resolution: dict[str, str | None]) -> None:
    """Write a metadata-only hook trace; never persist prompts, tool arguments, or tool output."""
    fields = {
        "agent": agent,
        "event": event,
        "session": session[:64],
        "project": resolution.get("project"),
        "source": resolution.get("source"),
        "cwd": resolution.get("cwd"),
        "agent_hint": resolution.get("agent_hint"),
    }
    _append_log("hooks.log", json.dumps(fields, separators=(",", ":"), ensure_ascii=False))
