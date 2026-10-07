"""Small reference catalogs, with two-level hierarchy enforced in MySQL too."""
from sqlalchemy import (
    Boolean, CHAR, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index,
    Integer, JSON, SmallInteger, String, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDTimestampMixin, UUIDCreatedAtMixin


class City(UUIDTimestampMixin, Base):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_cities_slug"),
        CheckConstraint("country_code = 'CN'", name="ck_cities_country"),
        CheckConstraint("sort_order BETWEEN 0 AND 10000", name="ck_cities_sort"),
        Index("ix_cities_active_sort", "is_active", "sort_order"),
    )
    slug: Mapped[str] = mapped_column(String(63, collation="ascii_bin"), nullable=False)
    name_en: Mapped[str] = mapped_column(String(80), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(80), nullable=False)
    province_en: Mapped[str] = mapped_column(String(80), nullable=False)
    province_zh: Mapped[str | None] = mapped_column(String(80))
    country_code: Mapped[str] = mapped_column(String(2), default="CN", server_default="CN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)


class Category(UUIDTimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_categories_slug"),
        UniqueConstraint("id", "level", name="uq_categories_id_level"),
        ForeignKeyConstraint(["parent_id", "parent_level"], ["categories.id", "categories.level"],
                             name="fk_categories_parent_root", ondelete="RESTRICT", onupdate="RESTRICT"),
        # A child can reference only a root; no self-reference, cycle or third level
        # is representable, including writes outside the application.
        CheckConstraint("(parent_id IS NULL AND parent_level IS NULL AND level = 1) OR "
                        "(parent_id IS NOT NULL AND parent_level = 1 AND level = 2)",
                        name="ck_categories_two_levels"),
        CheckConstraint("parent_id IS NULL OR parent_level IS NOT NULL", name="ck_categories_parent_complete"),
        CheckConstraint("sort_order BETWEEN 0 AND 10000", name="ck_categories_sort"),
        Index("ix_categories_parent", "parent_id", "parent_level"),
        Index("ix_categories_active_sort", "is_active", "sort_order"),
    )
    slug: Mapped[str] = mapped_column(String(63, collation="ascii_bin"), nullable=False)
    name_en: Mapped[str] = mapped_column(String(80), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    parent_id: Mapped[str | None] = mapped_column(CHAR(36))
    parent_level: Mapped[int | None] = mapped_column(SmallInteger)
    level: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text("1"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)


class CatalogWriteLock(Base):
    """One migration-seeded DB row serializes bounded, infrequent admin graph writes."""
    __tablename__ = "catalog_write_lock"
    __table_args__ = (CheckConstraint("id = 1", name="ck_catalog_write_lock_singleton"),)
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)


class AdminCatalogAudit(UUIDCreatedAtMixin, Base):
    __tablename__ = "admin_catalog_audit"
    __table_args__ = (Index("ix_admin_catalog_audit_resource", "resource_type", "resource_slug"),)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_slug: Mapped[str] = mapped_column(String(63), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
