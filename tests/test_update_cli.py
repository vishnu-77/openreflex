from __future__ import annotations

import subprocess
from unittest.mock import Mock

from openreflex import cli, updater


def test_check_for_update_detects_newer_release():
    status = updater.check_for_update("0.3.2", latest_fetcher=lambda: "0.3.3")
    assert status.current == "0.3.2"
    assert status.latest == "0.3.3"
    assert status.update_available is True


def test_check_for_update_does_not_downgrade_newer_build():
    status = updater.check_for_update("0.4.0", latest_fetcher=lambda: "0.3.3")
    assert status.update_available is False


def test_detect_install_plan_prefers_pipx(monkeypatch):
    monkeypatch.setattr(updater, "_direct_url", lambda: {})
    monkeypatch.setattr(updater, "_normalise_prefix", lambda: "/users/me/.local/pipx/venvs/openreflex")
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/usr/local/bin/pipx" if name == "pipx" else None)
    plan = updater.detect_install_plan()
    assert plan.method == "pipx"
    assert plan.command == ("/usr/local/bin/pipx", "upgrade", "openreflex")


def test_detect_install_plan_supports_uv_tool(monkeypatch):
    monkeypatch.setattr(updater, "_direct_url", lambda: {})
    monkeypatch.setattr(updater, "_normalise_prefix", lambda: "/users/me/.local/share/uv/tools/openreflex")
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/usr/local/bin/uv" if name == "uv" else None)
    plan = updater.detect_install_plan()
    assert plan.method == "uv-tool"
    assert plan.command == ("/usr/local/bin/uv", "tool", "upgrade", "openreflex")


def test_editable_install_is_never_replaced(monkeypatch):
    monkeypatch.setattr(updater, "_direct_url", lambda: {"url": "file:///work/openreflex", "dir_info": {"editable": True}})
    plan = updater.detect_install_plan()
    assert plan.method == "editable"
    assert plan.command is None


def test_run_update_uses_detected_command():
    runner = Mock(return_value=subprocess.CompletedProcess(["pipx"], 0))
    plan = updater.InstallPlan("pipx", ("pipx", "upgrade", "openreflex"), "Managed by pipx.")
    assert updater.run_update(plan, runner=runner) == 0
    runner.assert_called_once_with(["pipx", "upgrade", "openreflex"], check=False)


def test_update_parser_exposes_check_mode():
    args = cli.build_parser().parse_args(["update", "--check"])
    assert args.func is cli.cmd_update
    assert args.check is True


def test_update_check_never_runs_package_manager(monkeypatch, capsys):
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda current: updater.UpdateCheck(current=current, latest="9.9.9", update_available=True),
    )
    monkeypatch.setattr(
        updater,
        "detect_install_plan",
        lambda: updater.InstallPlan("pipx", ("pipx", "upgrade", "openreflex"), "Managed by pipx."),
    )
    run = Mock()
    monkeypatch.setattr(updater, "run_update", run)

    args = cli.build_parser().parse_args(["update", "--check"])
    assert args.func(args) == 0
    assert "update      available" in capsys.readouterr().out
    run.assert_not_called()
