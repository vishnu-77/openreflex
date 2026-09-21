from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_release_waits_for_successful_main_ci_and_creates_version_release():
    workflow = (ROOT / ".github/workflows/auto-release.yml").read_text(encoding="utf-8")

    assert 'workflows: ["CI"]' in workflow
    assert "branches: [main]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert 'ref: ${{ github.event.workflow_run.head_sha }}' in workflow
    assert 'git tag -a "$TAG" "$SHA"' in workflow
    assert 'gh release create "$TAG"' in workflow


def test_release_pipeline_validates_tag_and_verifies_pypi_before_mcp_registry():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'test "$TAG_NAME" = "v$VERSION"' in workflow
    assert "verify-pypi:" in workflow
    assert '"openreflex==$VERSION"' in workflow
    assert "os: [ubuntu-latest, macos-latest, windows-latest]" in workflow
    assert "needs: [build, verify-pypi]" in workflow
