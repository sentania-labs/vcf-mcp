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


def test_release_publishes_a_versioned_image_and_creates_a_release() -> None:
    text = RELEASE_WORKFLOW.read_text()
    assert '      - "v*.*.*"' in text
    assert "ghcr.io/sentania-labs/vcf-mcp:${{ github.ref_name }}" in text
    assert 'gh release create "$GITHUB_REF_NAME"' in text


def test_image_builds_use_the_shared_remote_buildkit() -> None:
    for workflow in (BUILD_WORKFLOW, RELEASE_WORKFLOW):
        text = workflow.read_text()
        setup_buildx = text.split("- name: Set up Docker Buildx", 1)[1].split(
            "- name: Login to GitHub Container Registry", 1
        )[0]
        assert "docker/setup-buildx-action@v3" in setup_buildx
        assert "driver: remote" in setup_buildx
        assert (
            "endpoint: tcp://buildkitd.buildkit.svc.cluster.local:1234"
            in setup_buildx
        )
        assert "docker/build-push-action@v6" in text


def test_smoke_job_pulls_and_runs_without_registry_credentials() -> None:
    text = RELEASE_WORKFLOW.read_text()
    smoke_job = text.split("  smoke:", 1)[1].split("  release:", 1)[0]
    assert "runs-on: ubuntu-latest" in smoke_job
    assert "docker/login-action" not in smoke_job
    assert 'docker pull "$image"' in smoke_job
    assert "docker run --detach" in smoke_job
    assert "curl --fail --silent --show-error" in smoke_job
    assert "http://127.0.0.1:18080/healthz" in smoke_job


def test_public_visibility_check_remains_daemon_free() -> None:
    text = RELEASE_WORKFLOW.read_text()
    verify_job = text.split("  verify:", 1)[1].split("  smoke:", 1)[0]
    assert "Publish and verify public package visibility" in verify_job
    assert "gh api" in verify_job
    assert "docker " not in verify_job


def test_only_the_outside_cluster_smoke_job_uses_github_hosted_runner() -> None:
    release_text = RELEASE_WORKFLOW.read_text()
    assert release_text.count("runs-on: ubuntu-latest") == 1

    for workflow in WORKFLOW_DIR.glob("*.yml"):
        for line in workflow.read_text().splitlines():
            if line.strip().startswith("runs-on:"):
                assert line.strip() in ("runs-on: lab", "runs-on: ubuntu-latest"), workflow
