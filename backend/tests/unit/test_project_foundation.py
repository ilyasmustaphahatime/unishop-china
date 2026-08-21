import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("relative_path", "expected_command"),
    [
        (
            "backend/Dockerfile",
            ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        ),
        (
            "frontend/Dockerfile",
            ["npm", "run", "dev", "--", "--host", "0.0.0.0"],
        ),
    ],
)
def test_dockerfile_has_valid_json_command(
    relative_path: str,
    expected_command: list[str],
) -> None:
    dockerfile = PROJECT_ROOT / relative_path
    command_lines = [
        line.removeprefix("CMD ")
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.startswith("CMD ")
    ]

    assert len(command_lines) == 1
    assert json.loads(command_lines[0]) == expected_command


def test_project_status_records_completed_phase_4d_audit() -> None:
    status = (PROJECT_ROOT / "documentation/CURRENT_PROJECT_STATUS.md").read_text(
        encoding="utf-8"
    )

    assert "Phase 4B backend refresh-token rotation" in status
    assert "Phase 4C secure frontend authentication: complete" in status
    assert "7/7 user-verified real-browser checks" in status
    assert "Phase 4D final authentication security audit: complete" in status
    assert "Ready for the separately approved Phase 5 authentication-recovery scope: yes" in status
    assert "Backend: 283 passed" in status
    assert "refresh tokens 6" in status
    assert "Phase 4D: not started" not in status
    assert "final real-browser workflow sign-off pending" not in status
    assert "Review and commit Phase 4B" not in status

    assert (PROJECT_ROOT / "documentation/phases/PHASE_4D_FINAL_AUTHENTICATION_AUDIT.md").is_file()
    assert (
        PROJECT_ROOT / "documentation/security/PHASE_4D_AUTHENTICATION_SECURITY_REVIEW.md"
    ).is_file()


def test_phase_4b_document_records_the_current_phase_4c_handoff() -> None:
    phase_4b = (PROJECT_ROOT / "documentation/phases/PHASE_4B_REFRESH_SESSIONS.md").read_text(
        encoding="utf-8"
    )

    assert "At Phase 4B completion" in phase_4b
    assert "uncommitted Phase 4C work with automated gates passing" in phase_4b
    assert "final real-browser gate subsequently passed using explicit user-verified evidence" in phase_4b
    assert "final real-browser sign-off remains pending" not in phase_4b
    assert "persistent authentication are not implemented" not in phase_4b
    assert "frontend does not yet send credentialed requests" not in phase_4b
