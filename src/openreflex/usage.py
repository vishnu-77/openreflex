"""Privacy-minimal Claude Code token accounting via local OTLP/HTTP JSON logs.

OpenReflex records counts and attribution only. Prompt/response/tool content logging remains disabled.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .models import UsageSample
from .project import home
from .store import Store, database_path

HOST = "127.0.0.1"
PORT = 4319
ENDPOINT = f"http://{HOST}:{PORT}/v1/logs"
OWNED_ENV = {
    "OPENREFLEX_TOKEN_TRACKING": "1",
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": ENDPOINT,
    "OTEL_LOG_USER_PROMPTS": "0",
    "OTEL_LOG_ASSISTANT_RESPONSES": "0",
    "OTEL_LOG_TOOL_DETAILS": "0",
    "OTEL_LOG_RAW_API_BODIES": "0",
}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _session_file(session_id: str) -> Path:
    key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
    return home() / "telemetry" / "sessions" / f"{key}.json"


def register_session(project: Path, session_id: str) -> None:
    if not session_id:
        return
    _atomic_json(_session_file(session_id), {
        "session_id": session_id,
        "project": str(project.resolve()),
        "updated_at": round(time.time(), 3),
    })


def _project_for_session(session_id: str) -> Path | None:
    try:
        data = json.loads(_session_file(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("session_id") != session_id or not isinstance(data.get("project"), str):
        return None
    return Path(data["project"])


def _value(item: Any) -> Any:
    if not isinstance(item, dict):
        return None
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in item:
            value = item[key]
            if key == "intValue":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
            return value
    return None


def _attributes(items: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(items, list):
        return result
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            result[item["key"]] = _value(item.get("value"))
    return result


def _records(payload: dict) -> list[tuple[dict[str, Any], int]]:
    result: list[tuple[dict[str, Any], int]] = []
    for resource in payload.get("resourceLogs", []) if isinstance(payload, dict) else []:
        if not isinstance(resource, dict):
            continue
        base = _attributes((resource.get("resource") or {}).get("attributes"))
        for scope in resource.get("scopeLogs", []):
            if not isinstance(scope, dict):
                continue
            for record in scope.get("logRecords", []):
                if not isinstance(record, dict):
                    continue
                attrs = {**base, **_attributes(record.get("attributes"))}
                body = _value(record.get("body"))
                if isinstance(body, str) and "event.name" not in attrs:
                    attrs["event.body"] = body
                raw_time = record.get("timeUnixNano") or record.get("observedTimeUnixNano") or 0
                try:
                    timestamp_ns = int(raw_time)
                except (TypeError, ValueError):
                    timestamp_ns = 0
                result.append((attrs, timestamp_ns))
    return result


def usage_totals(store: Store, execution_id: str) -> dict[str, Any]:
    samples = store.list("UsageSample", "execution_id", execution_id, limit=10000)
    return {
        "input": sum(x.input_tokens for x in samples),
        "output": sum(x.output_tokens for x in samples),
        "cache_read": sum(x.cache_read_tokens for x in samples),
        "cache_creation": sum(x.cache_creation_tokens for x in samples),
        "cost_usd": round(sum(x.estimated_cost_usd for x in samples), 6),
        "requests": len(samples),
        "models": sorted({x.model for x in samples if x.model}),
        "main_requests": sum(x.query_source in {"main", "repl_main_thread"} for x in samples),
        "subagent_requests": sum(x.query_source not in {"main", "repl_main_thread", "auxiliary", "compact"} for x in samples),
    }


def _sync_closed_nodes(store: Store, execution_id: str, totals: dict[str, Any]) -> None:
    fields = {
        "input_tokens": totals["input"],
        "output_tokens": totals["output"],
        "cache_read_tokens": totals["cache_read"],
        "cache_creation_tokens": totals["cache_creation"],
        "estimated_cost_usd": totals["cost_usd"],
    }
    outcome_id = "out-" + execution_id
    if store.exists(outcome_id):
        outcome = store.get(outcome_id)
        for key, value in fields.items():
            setattr(outcome, key, value)
        store.put(outcome)
    experience_id = "exp-" + execution_id
    if store.exists(experience_id):
        experience = store.get(experience_id)
        for key, value in fields.items():
            setattr(experience, key, value)
        store.put(experience)


def _record(attrs: dict[str, Any], timestamp_ns: int) -> bool:
    event = str(attrs.get("event.name") or attrs.get("event.body") or "")
    if event not in {"api_request", "claude_code.api_request"} and "api_request" not in event:
        return False
    session_id = str(attrs.get("session.id") or "")
    project = _project_for_session(session_id)
    if not project:
        return False

    store = Store(database_path(project))
    try:
        execution = store.latest("claude-code", session_id)
        if execution is None:
            return False
        request_id = str(attrs.get("request_id") or attrs.get("client_request_id") or "")
        sequence = str(attrs.get("event.sequence") or "")
        identity = "|".join((session_id, request_id, sequence, str(timestamp_ns), str(attrs.get("model") or "")))
        sample_id = "usage-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        if store.exists(sample_id):
            return False
        sample = UsageSample(
            id=sample_id,
            execution_id=execution.id,
            session_id=session_id,
            prompt_id=str(attrs.get("prompt.id") or ""),
            request_id=request_id,
            model=str(attrs.get("model") or ""),
            query_source=str(attrs.get("query_source") or "main"),
            input_tokens=max(0, int(attrs.get("input_tokens") or 0)),
            output_tokens=max(0, int(attrs.get("output_tokens") or 0)),
            cache_read_tokens=max(0, int(attrs.get("cache_read_tokens") or 0)),
            cache_creation_tokens=max(0, int(attrs.get("cache_creation_tokens") or 0)),
            estimated_cost_usd=max(0.0, float(attrs.get("cost_usd") or 0.0)),
            observed_at=(timestamp_ns / 1_000_000_000) if timestamp_ns else time.time(),
        )
        store.put(sample)
        totals = usage_totals(store, execution.id)
        _sync_closed_nodes(store, execution.id, totals)
    finally:
        store.close()

    try:
        from .project_memory import read_state, update_state
        state = read_state(project)
        update_state(project, token_usage=totals, token_execution_id=execution.id,
                     token_usage_updated_at=round(time.time(), 3),
                     token_tracking="active" if state.get("token_tracking") != "conflict" else "conflict")
    except Exception:
        pass
    return True


def ingest_otlp_logs(payload: dict) -> int:
    return sum(_record(attrs, timestamp_ns) for attrs, timestamp_ns in _records(payload))


class _Handler(BaseHTTPRequestHandler):
    server_version = "OpenReflexTokens/0.5"

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/logs":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4_000_000)
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            ingest_otlp_logs(payload if isinstance(payload, dict) else {})
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(400)
            self.end_headers()

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def receiver_running() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.08):
            return True
    except OSError:
        return False


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    server.serve_forever(poll_interval=0.5)


def ensure_receiver() -> bool:
    if receiver_running():
        return True
    command = [sys.executable, "-m", "openreflex", "tokens", "serve"]
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(command, **kwargs)  # noqa: S603
    except OSError:
        return False
    for _ in range(20):
        if receiver_running():
            return True
        time.sleep(0.025)
    return False


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _load_settings() -> dict:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f"{path} is not valid JSON") from error


def enable() -> dict[str, Any]:
    settings = _load_settings()
    env = settings.get("env")
    env = dict(env) if isinstance(env, dict) else {}
    owned = env.get("OPENREFLEX_TOKEN_TRACKING") == "1"
    protected = {"OTEL_LOGS_EXPORTER", "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL",
                 "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"}
    conflicts = sorted(key for key in protected if key in env and env.get(key) != OWNED_ENV.get(key) and not owned)
    if conflicts:
        return {"status": "conflict", "keys": conflicts, "path": str(_settings_path())}
    env.update(OWNED_ENV)
    settings["env"] = env
    _atomic_json(_settings_path(), settings)
    ensure_receiver()
    return {"status": "enabled", "endpoint": ENDPOINT, "path": str(_settings_path())}


def disable() -> dict[str, Any]:
    settings = _load_settings()
    env = settings.get("env")
    if not isinstance(env, dict) or env.get("OPENREFLEX_TOKEN_TRACKING") != "1":
        return {"status": "not-owned", "path": str(_settings_path())}
    env = dict(env)
    for key, value in OWNED_ENV.items():
        if env.get(key) == value:
            env.pop(key, None)
    if env:
        settings["env"] = env
    else:
        settings.pop("env", None)
    _atomic_json(_settings_path(), settings)
    return {"status": "disabled", "path": str(_settings_path())}


def configured() -> bool:
    try:
        env = _load_settings().get("env") or {}
        return isinstance(env, dict) and env.get("OPENREFLEX_TOKEN_TRACKING") == "1" \
            and env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") == ENDPOINT
    except ValueError:
        return False
