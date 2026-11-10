"""Repository imports cannot point upward, even under TYPE_CHECKING."""
import ast
from pathlib import Path

from app.common.pagination import BrowsePosition, PersonalizationPosition
from app.services import personalization_cursor, product_browse_cursor


def test_cursor_import_compatibility_uses_neutral_value_types():
    assert product_browse_cursor.BrowsePosition is BrowsePosition
    assert personalization_cursor.PersonalizationPosition is PersonalizationPosition


def test_repositories_do_not_import_service_or_api_layers():
    root = Path(__file__).resolve().parents[2] / "app" / "repositories"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            modules = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                       else [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            assert not any(module.startswith(("app.services", "app.api")) for module in modules), path.name
