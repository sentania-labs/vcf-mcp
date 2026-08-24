from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
BUILD_WORKFLOW = WORKFLOW_DIR / "build.yml"
RELEASE_WORKFLOW = WORKFLOW_DIR / "release.yml"


def test_setup_python_does_not_require_runner_local_pip_cache() -> None:
    text = BUILD_WORKFLOW.read_text()
    setup_python = text.split("- name: Set up Python", 1)[1].split(
        "- name: Install dependencies", 1
    )[0]
    assert "cache:" not in setup_python
    assert "actions/setup-python@v5" in setup_python
    assert "python -m pip install -e '.[test]'" in text


def test_test_job_gate_excludes_fork_pull_requests() -> None:
    text = BUILD_WORKFLOW.read_text()
    test_job = text.split("  test:", 1)[1].split("  build:", 1)[0]
    gate = next(
        line for line in test_job.splitlines() if line.strip().startswith("if:")
    )
    assert "github.repository == 'sentania-labs/vcf-mcp'" in gate
    assert "github.event_name != 'pull_request'" in gate
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository" in gate
    )


def test_build_workflow_publishes_the_repository_image_without_deploying() -> None:
    text = BUILD_WORKFLOW.read_text()
    assert "ghcr.io/sentania-labs/vcf-mcp:${{ github.sha }}" in text
    for deployment_reference in (
        "DOCKER_DEPLOY_KEY",
        "DOCKER_DEPLOY_HOST",
        "SERVICE_URL",
        "images.env",
        "scp ",
        "ssh ",
    ):
        assert deployment_reference not in text


def test_release_publishes_and_anonymously_pulls_a_versioned_image() -> None:
    text = RELEASE_WORKFLOW.read_text()
    assert '      - "v*.*.*"' in text
    assert "ghcr.io/sentania-labs/vcf-mcp:${{ github.ref_name }}" in text
    assert 'DOCKER_CONFIG="$anonymous_config" docker pull "$image"' in text
    assert 'gh release create "$GITHUB_REF_NAME"' in text


def test_every_workflow_job_targets_the_lab_runner_pool() -> None:
    for workflow in WORKFLOW_DIR.glob("*.yml"):
        for line in workflow.read_text().splitlines():
            if line.strip().startswith("runs-on:"):
                assert line.strip() == "runs-on: lab", workflow
