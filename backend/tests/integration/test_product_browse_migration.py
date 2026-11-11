"""Real index round-trip on an isolated server, never the development schema."""
import importlib.util
import os
from pathlib import Path
import shutil

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.core.config import settings
from app.core.database import Base, engine
from scripts.offers_migration_checks import disposable_server
from tests.conftest import _database_snapshot

MIGRATION = (Path(__file__).resolve().parents[2] / "alembic" / "versions" /
             "b11b2c3d4e5f_product_browse_indexes.py")
INDEXES = {"ix_product_listings_browse_newest", "ix_product_listings_browse_price",
           "ix_product_listings_search_ngram", "ix_product_listings_city_newest",
           "ix_product_listings_city_price", "ix_product_listings_category_newest",
           "ix_product_listings_category_price"}


def test_additive_indexes_upgrade_downgrade_upgrade_on_isolated_mysql_database():
    assert settings.app_env == "development" and engine.url.database == "unishop_china"
    before = _database_snapshot()
    candidates = sorted(Path(os.environ.get("ProgramFiles", "C:/Program Files")).glob(
        "MySQL/MySQL Server */bin/mysqld.exe"))
    binary = os.environ.get("UNISHOP_TEST_MYSQLD") or shutil.which("mysqld") or next(iter(candidates), None)
    assert binary, "Set UNISHOP_TEST_MYSQLD to an installed native MySQL server binary."
    spec = importlib.util.spec_from_file_location("phase11b_probe_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with disposable_server(binary) as url:
        assert url.port != engine.url.port and url.port != 3306
        isolated = create_engine(url, pool_pre_ping=True)
        try:
            # Only the temporary server receives DDL. Metadata includes the
            # catalog/user FK targets required by the isolated listing table.
            Base.metadata.create_all(isolated)
            with isolated.connect() as conn:
                for index in INDEXES:
                    conn.exec_driver_sql(f"ALTER TABLE `product_listings` DROP INDEX `{index}`")
                module.op = Operations(MigrationContext.configure(conn))
                for action, expected in ((module.upgrade, True), (module.downgrade, False),
                                         (module.upgrade, True)):
                    action()
                    present = {row["name"] for row in inspect(conn).get_indexes("product_listings")}
                    assert INDEXES.issubset(present) if expected else INDEXES.isdisjoint(present)
        finally:
            isolated.dispose()
    assert _database_snapshot() == before
