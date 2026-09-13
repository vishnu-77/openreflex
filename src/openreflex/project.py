"""Project identity, per-project approval, and local logging. Nothing is captured for unapproved projects."""

import hashlib
import json
import os
import time
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("OPENREFLEX_HOME", str(Path.home() / ".openreflex")))


def project_root(cwd: str | os.PathLike | None = None) -> Path:
    """The enclosing repository root when there is one, so subdirectory sessions share one memory."""
    explicit = os.environ.get("OPENREFLEX_PROJECT") or os.environ.get("CLAUDE_PROJECT_DIR")
    start = Path(explicit or cwd or os.getcwd()).resolve()
    if explicit:
        return start
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / ".openreflex.json").exists():
            return candidate
    return start


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
    path = _approvals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


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
    """Rate-limits the 'not enabled for this project' notice so it never nags."""
    # hashlib, not hash(): str hashes are randomized per process and hooks are separate processes.
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


def log_error(message: str) -> None:
    path = home() / "logs" / "errors.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
    except OSError:
        pass
