from openreflex import project_memory


def test_first_session_starts_one_detached_primer_and_returns_reflexing(project, monkeypatch):
    calls = []

    class FakeProcess:
        pass

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(project_memory.subprocess, "Popen", fake_popen)

    first = project_memory.ensure_background_refresh(project)
    second = project_memory.ensure_background_refresh(project)

    assert first == "reflexing"
    assert second == "reflexing"
    assert len(calls) == 1, "the primer lock must prevent duplicate workers"
    command, kwargs = calls[0]
    assert command[:3] == [project_memory.sys.executable, "-m", "openreflex"]
    assert "primer-worker" in command
    assert kwargs["stdin"] is project_memory.subprocess.DEVNULL
    assert kwargs["stdout"] is project_memory.subprocess.DEVNULL
    assert kwargs["stderr"] is project_memory.subprocess.DEVNULL
    if project_memory.os.name != "nt":
        assert kwargs["start_new_session"] is True


def test_fresh_snapshot_does_not_launch_worker(project, monkeypatch):
    (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    project_memory.build_snapshot(project)

    def unexpected(*args, **kwargs):
        raise AssertionError("fresh project memory must not launch a worker")

    monkeypatch.setattr(project_memory.subprocess, "Popen", unexpected)
    assert project_memory.ensure_background_refresh(project) == "ready"
