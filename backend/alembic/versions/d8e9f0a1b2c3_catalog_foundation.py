"""Phase 8: reference catalogs, transactional admin audit and preserved profile cities."""
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

# Frozen migration data, not an application allowlist. No startup-time seeding.
CITIES = (
    ("qingdao", "Qingdao", "青岛", "Shandong", "山东"),
    ("beijing", "Beijing", "北京", "Beijing", "北京"),
    ("shanghai", "Shanghai", "上海", "Shanghai", "上海"),
    ("shenzhen", "Shenzhen", "深圳", "Guangdong", "广东"),
    ("guangzhou", "Guangzhou", "广州", "Guangdong", "广东"),
    ("hangzhou", "Hangzhou", "杭州", "Zhejiang", "浙江"),
)


def profile_city_preflight():
    statement = sa.text("SELECT COUNT(*) FROM user_profiles WHERE city IS NOT NULL "
                        "AND BINARY city NOT IN :names").bindparams(sa.bindparam("names", expanding=True))
    count = op.get_bind().scalar(statement, {"names": [row[1] for row in CITIES]})
    if count:
        # Stop before MySQL's auto-committing DDL. Do not print private row values.
        raise RuntimeError(f"Catalog migration refused: {count} unmapped profile cities. No data was changed.")


def timestamps():
    return (sa.Column("id", sa.CHAR(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def upgrade():
    profile_city_preflight()
    op.create_table("cities", *timestamps(),
        sa.Column("slug", sa.String(63, collation="ascii_bin"), nullable=False),
        sa.Column("name_en", sa.String(80), nullable=False),
        sa.Column("name_zh", sa.String(80), nullable=False),
        sa.Column("province_en", sa.String(80), nullable=False),
        sa.Column("province_zh", sa.String(80)),
        sa.Column("country_code", sa.String(2), server_default="CN", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_cities_slug"),
        sa.CheckConstraint("country_code = 'CN'", name="ck_cities_country"),
        sa.CheckConstraint("sort_order BETWEEN 0 AND 10000", name="ck_cities_sort"))
    op.create_index("ix_cities_active_sort", "cities", ["is_active", "sort_order"])
    statement = sa.text("INSERT INTO cities "
        "(id,slug,name_en,name_zh,province_en,province_zh,country_code,is_active,sort_order,created_at,updated_at) "
        "VALUES (:id,:slug,:name_en,:name_zh,:province_en,:province_zh,'CN',1,:sort_order,"
        "'2026-10-07 00:00:00','2026-10-07 00:00:00')")
    for order, (slug, name_en, name_zh, province_en, province_zh) in enumerate(CITIES):
        op.get_bind().execute(statement, dict(id=str(uuid5(NAMESPACE_URL, "unishop:phase8:city:" + slug)),
            slug=slug, name_en=name_en, name_zh=name_zh, province_en=province_en,
            province_zh=province_zh, sort_order=order))

    op.create_table("categories", *timestamps(),
        sa.Column("slug", sa.String(63, collation="ascii_bin"), nullable=False),
        sa.Column("name_en", sa.String(80), nullable=False),
        sa.Column("name_zh", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("parent_id", sa.CHAR(36)), sa.Column("parent_level", sa.SmallInteger()),
        sa.Column("level", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.UniqueConstraint("id", "level", name="uq_categories_id_level"),
        sa.ForeignKeyConstraint(["parent_id", "parent_level"], ["categories.id", "categories.level"],
            name="fk_categories_parent_root", ondelete="RESTRICT", onupdate="RESTRICT"),
        sa.CheckConstraint("(parent_id IS NULL AND parent_level IS NULL AND level = 1) OR "
            "(parent_id IS NOT NULL AND parent_level = 1 AND level = 2)", name="ck_categories_two_levels"),
        sa.CheckConstraint("sort_order BETWEEN 0 AND 10000", name="ck_categories_sort"))
    op.create_index("ix_categories_parent", "categories", ["parent_id", "parent_level"])
    op.create_index("ix_categories_active_sort", "categories", ["is_active", "sort_order"])
    op.create_table("catalog_write_lock", sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
                    sa.CheckConstraint("id = 1", name="ck_catalog_write_lock_singleton"))
    op.execute(sa.text("INSERT INTO catalog_write_lock (id) VALUES (1)"))
    op.create_table("admin_catalog_audit",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(16), nullable=False),
        sa.Column("resource_slug", sa.String(63), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False))
    op.create_index("ix_admin_catalog_audit_resource", "admin_catalog_audit", ["resource_type", "resource_slug"])

    op.add_column("user_profiles", sa.Column("city_id", sa.CHAR(36), nullable=True))
    op.execute(sa.text("UPDATE user_profiles p JOIN cities c ON BINARY p.city = BINARY c.name_en "
                       "SET p.city_id = c.id WHERE p.city IS NOT NULL"))
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM user_profiles WHERE city IS NOT NULL AND city_id IS NULL")):
        raise RuntimeError("Catalog backfill incomplete; stop and inspect migration state.")
    op.create_index("ix_user_profiles_city", "user_profiles", ["city_id"])
    op.create_foreign_key("fk_user_profiles_city", "user_profiles", "cities", ["city_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("ck_user_profiles_supported_city", "user_profiles", type_="check")
    op.alter_column("user_profiles", "city", existing_type=sa.String(32), type_=sa.String(80), existing_nullable=True)
    op.create_check_constraint("ck_user_profiles_city_reference", "user_profiles",
        "(city IS NULL AND city_id IS NULL) OR (city IS NOT NULL AND city_id IS NOT NULL)")


def downgrade():
    # Older code cannot represent new cities. Refuse instead of silently deleting
    # legitimate new references; round-trips are exercised only on disposable DBs.
    profile_city_preflight()
    op.drop_constraint("ck_user_profiles_city_reference", "user_profiles", type_="check")
    op.drop_constraint("fk_user_profiles_city", "user_profiles", type_="foreignkey")
    op.drop_index("ix_user_profiles_city", "user_profiles")
    op.drop_column("user_profiles", "city_id")
    op.alter_column("user_profiles", "city", existing_type=sa.String(80), type_=sa.String(32), existing_nullable=True)
    op.create_check_constraint("ck_user_profiles_supported_city", "user_profiles",
        "city IS NULL OR city IN ('Qingdao','Beijing','Shanghai','Shenzhen','Guangzhou','Hangzhou')")
    op.drop_table("admin_catalog_audit")
    op.drop_table("catalog_write_lock")
    op.drop_table("categories")
    op.drop_table("cities")
