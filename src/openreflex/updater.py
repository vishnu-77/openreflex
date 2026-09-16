from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PYPI_JSON_URL = "https://pypi.org/pypi/openreflex/json"


@dataclass(frozen=True)
class InstallPlan:
    method: str
    command: tuple[str, ...] | None
    detail: str
    reinstall_command: tuple[str, ...] | None = None
    uninstall_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class UpdateCheck:
    current: str
    latest: str
    update_available: bool


def _normalise_prefix() -> str:
    return str(Path(sys.prefix)).replace("\\", "/").lower()


def _direct_url() -> dict:
    try:
        dist = metadata.distribution("openreflex")
        raw = dist.read_text("direct_url.json")
    except (metadata.PackageNotFoundError, OSError):
        return {}
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def detect_install_plan() -> InstallPlan:
    """Return the safest supported package-manager plan for this OpenReflex install."""
    direct = _direct_url()
    url = str(direct.get("url") or "")
    dir_info = direct.get("dir_info") if isinstance(direct.get("dir_info"), dict) else {}
    if dir_info.get("editable"):
        return InstallPlan(
            "editable",
            None,
            "Editable/development install detected; update the source checkout instead of replacing it.",
        )

    prefix = _normalise_prefix()
    if "/uv/archive" in prefix or "/.cache/uv/archive" in prefix:
        return InstallPlan(
            "uvx",
            None,
            "Ephemeral uvx environment detected; use a persistent `uv tool install openreflex` install to self-manage.",
        )

    pipx = shutil.which("pipx")
    if pipx and ("/pipx/venvs/openreflex" in prefix or "/pipx/venvs/" in prefix):
        return InstallPlan(
            "pipx",
            (pipx, "upgrade", "openreflex"),
            "Managed by pipx.",
            reinstall_command=(pipx, "reinstall", "openreflex"),
            uninstall_command=(pipx, "uninstall", "openreflex"),
        )

    uv = shutil.which("uv")
    if uv and "/uv/tools/openreflex" in prefix:
        return InstallPlan(
            "uv-tool",
            (uv, "tool", "upgrade", "openreflex"),
            "Managed by uv tool.",
            reinstall_command=(uv, "tool", "install", "--force", "openreflex"),
            uninstall_command=(uv, "tool", "uninstall", "openreflex"),
        )

    if direct.get("vcs_info") or (url and not url.startswith("file:")):
        return InstallPlan(
            "source",
            None,
            "Source/VCS install detected; automatic replacement is disabled so the chosen source is not overwritten.",
        )
    if url.startswith("file:"):
        return InstallPlan(
            "local",
            None,
            "Local-path install detected; update or reinstall from that local source explicitly.",
        )

    # OpenReflex documents pipx and uv tool as the supported persistent installs.
    # Refuse to mutate an arbitrary system/virtualenv Python automatically.
    return InstallPlan(
        "unknown",
        None,
        "Install method is not safely identifiable. Reinstall with `pipx install openreflex` or `uv tool install openreflex`.",
    )


def latest_pypi_version(*, timeout: float = 5.0) -> str:
    request = Request(PYPI_JSON_URL, headers={"User-Agent": "openreflex-update"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed trusted HTTPS endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"could not check PyPI: {exc}") from exc
    version = payload.get("info", {}).get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("could not check PyPI: response did not contain a version")
    return version.strip()


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def _version_key(value: str) -> tuple[int, int, int, int, str] | None:
    """Small stable-release comparator without adding a packaging dependency.

    OpenReflex publishes normal x.y.z releases. A suffix sorts before the corresponding
    stable version so 0.4.0rc1 does not appear newer than 0.4.0.
    """
    match = _VERSION_RE.match(value.strip())
    if not match:
        return None
    major, minor, patch = (int(match.group(i)) for i in range(1, 4))
    suffix = match.group(4)
    return major, minor, patch, 1 if not suffix else 0, suffix


def check_for_update(current: str, *, latest_fetcher: Callable[[], str] = latest_pypi_version) -> UpdateCheck:
    latest = latest_fetcher()
    current_key = _version_key(current)
    latest_key = _version_key(latest)
    if current_key is None or latest_key is None:
        available = current != latest
    else:
        available = latest_key > current_key
    return UpdateCheck(current=current, latest=latest, update_available=available)


def run_command(
    command: tuple[str, ...] | None,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    if command is None:
        return 2
    try:
        result = runner(list(command), check=False)
    except OSError:
        return 1
    return int(result.returncode)


def run_update(plan: InstallPlan, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    return run_command(plan.command, runner=runner)


def run_reinstall(plan: InstallPlan, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    return run_command(plan.reinstall_command, runner=runner)


def run_uninstall(plan: InstallPlan, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    return run_command(plan.uninstall_command, runner=runner)


def installed_version_after_update(*, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str | None:
    executable = shutil.which("openreflex")
    if not executable:
        return None
    try:
        result = runner([executable, "--version"], check=False, capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None
