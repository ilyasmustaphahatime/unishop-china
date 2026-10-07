from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import City, Category, CatalogWriteLock, AdminCatalogAudit


class CityRepository:
    def get(self, db: Session, slug: str, *, lock=False) -> City | None:
        statement = select(City).where(City.slug == slug)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return db.scalar(statement)

    def by_id(self, db: Session, city_id: str, *, lock=False) -> City | None:
        statement = select(City).where(City.id == city_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return db.scalar(statement)

    def list(self, db: Session, *, include_inactive=False) -> list[City]:
        statement = select(City).order_by(City.sort_order, City.slug)
        if not include_inactive:
            statement = statement.where(City.is_active.is_(True))
        return list(db.scalars(statement))

    def count(self, db: Session) -> int:
        return len(list(db.scalars(select(City.id).with_for_update())))


class CategoryRepository:
    def get(self, db: Session, slug: str) -> Category | None:
        return db.scalar(select(Category).where(Category.slug == slug).with_for_update()
                         .execution_options(populate_existing=True))

    def list(self, db: Session, *, lock=False) -> list[Category]:
        statement = select(Category).order_by(Category.sort_order, Category.slug)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(db.scalars(statement))

    def has_children(self, db: Session, category_id: str, *, active_only=False) -> bool:
        statement = select(Category.id).where(Category.parent_id == category_id)
        if active_only:
            statement = statement.where(Category.is_active.is_(True))
        return db.scalar(statement.limit(1).with_for_update()) is not None


class CatalogAuditRepository:
    def lock_writes(self, db: Session) -> None:
        if db.scalar(select(CatalogWriteLock.id).where(CatalogWriteLock.id == 1).with_for_update()) != 1:
            raise RuntimeError("Catalog write lock unavailable.")

    def record(self, db: Session, *, actor_id: str, action: str, resource_type: str,
               slug: str, fields: list[str]) -> None:
        # Only server-selected field names, never raw admin payloads or prior values.
        db.add(AdminCatalogAudit(actor_id=actor_id, action=action, resource_type=resource_type,
                                 resource_slug=slug, details={"fields": sorted(fields)}))
        db.flush()
