from pathlib import Path
import re


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


def _dockerignore_rules() -> list[str]:
    return [
        line.strip()
        for line in (BACKEND_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_backend_dockerignore_has_required_secret_and_artifact_policy() -> None:
    dockerignore = BACKEND_DIR / ".dockerignore"

    assert dockerignore.is_file()
    rules = _dockerignore_rules()
    assert ".env" in rules
    assert ".env.*" in rules
    assert "!.env.example" in rules
    assert rules.index("!.env.example") > rules.index(".env.*")
    for required in (
        ".venv/",
        "venv/",
        "**/__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "uploads/",
        "private_uploads/",
    ):
        assert required in rules


def test_backend_dockerfile_does_not_copy_or_hardcode_secrets() -> None:
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    executable_lines = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert not any(re.match(r"^(COPY|ADD)\s+.*\.env(?:\s|$)", line, re.I) for line in executable_lines)
    assert not any(
        re.match(
            r"^ENV\s+.*(?:PASSWORD|SECRET|TOKEN|API_KEY|CREDENTIAL)\s*=",
            line,
            re.I,
        )
        for line in executable_lines
    )


def test_compose_uses_guarded_backend_context_and_runtime_substitution() -> None:
    compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    assert "build: ./backend" in compose
    for line in compose.splitlines():
        if re.search(r"MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD|DATABASE_URL", line):
            assert "${" in line
