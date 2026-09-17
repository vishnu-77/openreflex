import json
import tomllib
from pathlib import Path

from openreflex import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_runtime_and_manifests():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifests = [
        ROOT / "plugins/openreflex/.claude-plugin/plugin.json",
        ROOT / "plugins/openreflex/.codex-plugin/plugin.json",
        ROOT / "plugins/openreflex/.cursor-plugin/plugin.json",
    ]
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == __version__
    for path in manifests:
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == __version__
    assert server["version"] == __version__
    assert server["packages"][0]["version"] == __version__
