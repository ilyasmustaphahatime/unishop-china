"""Explicit catalog rules; each mutation and its audit are one transaction."""
from contextlib import contextmanager

from app.core.authorization import lock_active_user, require_db_admin
from app.core.transactions import retry_deadlock, transaction
from app.models.catalog import City, Category
from app.repositories.catalog_repository import CityRepository, CategoryRepository, CatalogAuditRepository
from app.schemas.catalog import AdminCity, PublicCity, AdminCategory, PublicCategory, CategoryTree


class CatalogError(Exception):
    def __init__(self, message: str, status=409):
        super().__init__(message)
        self.status = status


@contextmanager
def catalog_mutation(db, actor_id):
    with transaction(db):
        lock_active_user(db, actor_id)
        require_db_admin(db, actor_id)
        # Category structure and bounded catalog capacities share one DB mutex.
        # It survives multiple workers; process-local locks would not be sufficient.
        CatalogAuditRepository().lock_writes(db)
        yield


def record_change(db, actor_id, action, resource, slug, fields):
    CatalogAuditRepository().record(db, actor_id=actor_id, action=action,
                                    resource_type=resource, slug=slug, fields=fields)


def require_resource(row):
    if row is None:
        raise CatalogError("Catalog resource not found.", 404)
    return row


class CityService:
    def __init__(self):
        self.repo = CityRepository()

    @staticmethod
    def response(row, *, admin=False):
        values = dict(slug=row.slug, name_en=row.name_en, name_zh=row.name_zh,
                      province_en=row.province_en, province_zh=row.province_zh, country_code=row.country_code)
        if admin:
            return AdminCity(**values, is_active=row.is_active, sort_order=row.sort_order)
        return PublicCity(**values)

    def list_public(self, db):
        return [self.response(row) for row in self.repo.list(db)]

    def get_public(self, db, slug):
        row = self.repo.get(db, slug)
        require_resource(row if row and row.is_active else None)
        return self.response(row)

    def list_admin(self, db, actor_id):
        with transaction(db):
            lock_active_user(db, actor_id)
            require_db_admin(db, actor_id)
            return [self.response(row, admin=True) for row in self.repo.list(db, include_inactive=True)]

    @retry_deadlock
    def create(self, db, actor_id, body):
        with catalog_mutation(db, actor_id):
            if self.repo.get(db, body.slug, lock=True):
                raise CatalogError("City slug already exists.")
            if self.repo.count(db) >= 200:
                raise CatalogError("City catalog capacity reached.")
            row = City(slug=body.slug, name_en=body.name_en, name_zh=body.name_zh,
                       province_en=body.province_en, province_zh=body.province_zh,
                       country_code="CN", sort_order=body.sort_order)
            db.add(row)
            db.flush()
            record_change(db, actor_id, "CITY_CREATED", "city", row.slug, list(body.model_fields_set))
            return self.response(row, admin=True)

    @retry_deadlock
    def update(self, db, actor_id, slug, body):
        with catalog_mutation(db, actor_id):
            row = require_resource(self.repo.get(db, slug, lock=True))
            # Explicit allowlist: schema changes cannot silently widen persistence.
            for field in ("name_en", "name_zh", "province_en", "province_zh", "sort_order"):
                if field in body.model_fields_set:
                    setattr(row, field, getattr(body, field))
            record_change(db, actor_id, "CITY_UPDATED", "city", slug, list(body.model_fields_set))
            return self.response(row, admin=True)

    @retry_deadlock
    def set_active(self, db, actor_id, slug, active):
        with catalog_mutation(db, actor_id):
            row = require_resource(self.repo.get(db, slug, lock=True))
            row.is_active = active
            record_change(db, actor_id, "CITY_ACTIVATED" if active else "CITY_DEACTIVATED",
                          "city", slug, ["is_active"])
            return self.response(row, admin=True)

    def resolve_profile_city(self, db, slug):
        # Hold this row lock through the profile transaction. Deactivation and a
        # new assignment must serialize on authoritative current state.
        row = self.repo.get(db, slug, lock=True)
        if row is None or not row.is_active:
            raise CatalogError("Choose an active city.", 422)
        return row


class CategoryService:
    def __init__(self):
        self.repo = CategoryRepository()

    @staticmethod
    def response(row, rows, *, admin=False):
        parent = next((item for item in rows if item.id == row.parent_id), None)
        values = dict(slug=row.slug, name_en=row.name_en, name_zh=row.name_zh,
                      description=row.description, parent_slug=parent.slug if parent else None)
        if admin:
            return AdminCategory(**values, is_active=row.is_active, sort_order=row.sort_order)
        return PublicCategory(**values)

    def visible_rows(self, db):
        rows = self.repo.list(db)
        roots = {row.id for row in rows if row.is_active and row.parent_id is None}
        return [row for row in rows if row.is_active and (row.parent_id is None or row.parent_id in roots)]

    def list_public(self, db):
        rows = self.visible_rows(db)  # One bounded query; never recursive ORM serialization.
        children = {}
        for row in rows:
            if row.parent_id is not None:
                children.setdefault(row.parent_id, []).append(self.response(row, rows))
        return [CategoryTree(**self.response(row, rows).model_dump(), children=children.get(row.id, []))
                for row in rows if row.parent_id is None]

    def get_public(self, db, slug):
        rows = self.visible_rows(db)
        row = require_resource(next((row for row in rows if row.slug == slug), None))
        return self.response(row, rows)

    def list_admin(self, db, actor_id):
        with transaction(db):
            lock_active_user(db, actor_id)
            require_db_admin(db, actor_id)
            rows = self.repo.list(db)
            return [self.response(row, rows, admin=True) for row in rows]

    def validate_parent(self, db, row, parent_slug):
        if parent_slug is None:
            return None
        if row.slug == parent_slug:
            raise CatalogError("A category cannot be its own parent.")
        parent = require_resource(self.repo.get(db, parent_slug))
        if not parent.is_active or parent.level != 1:
            raise CatalogError("Choose an active root category.")
        if row.id and self.repo.has_children(db, row.id):
            raise CatalogError("A category with children must remain a root.")
        return parent

    @staticmethod
    def assign_parent(row, parent):
        row.parent_id = parent.id if parent else None
        row.parent_level = 1 if parent else None
        row.level = 2 if parent else 1

    @retry_deadlock
    def create(self, db, actor_id, body):
        with catalog_mutation(db, actor_id):
            if self.repo.get(db, body.slug):
                raise CatalogError("Category slug already exists.")
            if len(self.repo.list(db, lock=True)) >= 500:
                raise CatalogError("Category catalog capacity reached.")
            row = Category(slug=body.slug, name_en=body.name_en, name_zh=body.name_zh,
                           description=body.description, sort_order=body.sort_order)
            self.assign_parent(row, self.validate_parent(db, row, body.parent_slug))
            db.add(row)
            db.flush()
            record_change(db, actor_id, "CATEGORY_CREATED", "category", row.slug, list(body.model_fields_set))
            return self.response(row, self.repo.list(db, lock=True), admin=True)

    @retry_deadlock
    def update(self, db, actor_id, slug, body):
        with catalog_mutation(db, actor_id):
            row = require_resource(self.repo.get(db, slug))
            old_parent = row.parent_id
            if "parent_slug" in body.model_fields_set:
                self.assign_parent(row, self.validate_parent(db, row, body.parent_slug))
            for field in ("name_en", "name_zh", "description", "sort_order"):
                if field in body.model_fields_set:
                    setattr(row, field, getattr(body, field))
            action = "CATEGORY_REPARENTED" if row.parent_id != old_parent else "CATEGORY_UPDATED"
            record_change(db, actor_id, action, "category", slug, list(body.model_fields_set))
            return self.response(row, self.repo.list(db, lock=True), admin=True)

    @retry_deadlock
    def set_active(self, db, actor_id, slug, active):
        with catalog_mutation(db, actor_id):
            row = require_resource(self.repo.get(db, slug))
            rows = self.repo.list(db, lock=True)
            parent = next((item for item in rows if item.id == row.parent_id), None)
            if active and parent is not None and not parent.is_active:
                raise CatalogError("Activate the parent first.")
            if not active and self.repo.has_children(db, row.id, active_only=True):
                raise CatalogError("Deactivate active children first.")
            row.is_active = active
            record_change(db, actor_id, "CATEGORY_ACTIVATED" if active else "CATEGORY_DEACTIVATED",
                          "category", slug, ["is_active"])
            return self.response(row, rows, admin=True)
