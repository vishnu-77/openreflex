from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_release_waits_for_successful_main_ci_and_dispatches_trusted_publisher():
    workflow = (ROOT / ".github/workflows/auto-release.yml").read_text(encoding="utf-8")

    assert 'workflows: ["CI"]' in workflow
    assert "branches: [main]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert 'ref: ${{ github.event.workflow_run.head_sha }}' in workflow
    assert "gh release view" in workflow
    assert "gh workflow run release.yml" in workflow
    assert "--ref main" in workflow
    assert "-f target=pypi" in workflow
    assert "-f create_github_release=true" in workflow
    assert '-f release_ref="$RELEASE_SHA"' in workflow
    assert "uses: ./.github/workflows/release.yml" not in workflow


def test_release_pipeline_preserves_release_workflow_oidc_identity_and_finishes_with_github_release():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_call:" not in workflow
    assert "release_ref:" in workflow
    assert "create_github_release:" in workflow
    assert 'ref: ${{ inputs.release_ref || github.ref }}' in workflow
    assert 'test "$TAG_NAME" = "$EXPECTED_TAG"' in workflow
    assert "verify-pypi:" in workflow
    assert '"openreflex==$VERSION"' in workflow
    assert "os: [ubuntu-latest, macos-latest, windows-latest]" in workflow
    assert "needs: [build, verify-pypi]" in workflow
    assert "registry.modelcontextprotocol.io/v0.1/servers/" in workflow
    assert "is already present in the MCP Registry" in workflow
    assert "github-release:" in workflow
    assert "needs: [build, mcp-registry]" in workflow
    assert 'gh release create "$TAG"' in workflow


def test_github_release_is_declared_only_after_registry_publication():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    mcp = workflow.index("  mcp-registry:")
    github_release = workflow.index("  github-release:")

    assert mcp < github_release
    assert "needs: [build, mcp-registry]" in workflow[github_release:]
