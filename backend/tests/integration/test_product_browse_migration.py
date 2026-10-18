"""Real MySQL additive index round-trip on a disposable table, never live listings."""
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from app.core.config import settings
from app.core.database import engine
from tests.conftest import _database_snapshot

MIGRATION = (Path(__file__).resolve().parents[2] / "alembic" / "versions" /
             "b11b2c3d4e5f_product_browse_indexes.py")
INDEXES = {"ix_product_listings_browse_newest", "ix_product_listings_browse_price",
           "ix_product_listings_search_ngram", "ix_product_listings_city_newest",
           "ix_product_listings_city_price", "ix_product_listings_category_newest",
           "ix_product_listings_category_price"}


def test_additive_indexes_upgrade_downgrade_upgrade_on_disposable_mysql_table():
    assert settings.app_env == "development" and engine.url.database == "unishop_china"
    before = _database_snapshot()
    name = "phase11b_probe_" + uuid4().hex[:12]
    spec = importlib.util.spec_from_file_location("phase11b_probe_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TABLE = name
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql(f"CREATE TABLE `{name}` LIKE product_listings")
            for index in INDEXES:
                conn.exec_driver_sql(f"ALTER TABLE `{name}` DROP INDEX `{index}`")
            module.op = Operations(MigrationContext.configure(conn))
            for action, expected in ((module.upgrade, True), (module.downgrade, False),
                                     (module.upgrade, True)):
                action()
                present = {row["name"] for row in inspect(conn).get_indexes(name)}
                assert INDEXES.issubset(present) if expected else INDEXES.isdisjoint(present)
        finally:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{name}`")
            conn.commit()
    assert not inspect(engine).has_table(name)
    assert _database_snapshot() == before
