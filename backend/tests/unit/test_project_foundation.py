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


def test_project_status_hands_off_from_phase_4b_to_phase_4c() -> None:
    status = (PROJECT_ROOT / "documentation/CURRENT_PROJECT_STATUS.md").read_text(
        encoding="utf-8"
    )

    assert "Phase 4B backend refresh-token rotation" in status
    assert "Phase 4C frontend session bootstrap and coordinated refresh: not started" in status
    assert "Review and commit Phase 4B" not in status
