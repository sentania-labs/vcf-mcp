from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-deploy.yml"


def test_setup_python_does_not_require_runner_local_pip_cache() -> None:
    text = WORKFLOW.read_text()
    setup_python = text.split("- name: Set up Python", 1)[1].split(
        "- name: Install dependencies", 1
    )[0]
    assert "cache:" not in setup_python
    assert "actions/setup-python@v5" in setup_python
    assert "python -m pip install -e .[test]" in text


def test_test_job_gate_excludes_fork_pull_requests() -> None:
    text = WORKFLOW.read_text()
    test_job = text.split("  test:", 1)[1].split("  build:", 1)[0]
    gate = next(
        line for line in test_job.splitlines() if line.strip().startswith("if:")
    )
    assert "github.repository == 'sentania-labs/vcf-ops-mcp'" in gate
    assert "github.event_name != 'pull_request'" in gate
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository" in gate
    )


def test_deploy_does_not_require_a_hand_authored_session_env_file() -> None:
    text = WORKFLOW.read_text()
    assert "$SLOT/.env" not in text
    assert "--env-file $SLOT/images.env" in text
