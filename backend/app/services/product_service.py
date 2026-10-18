"""Listing lifecycle and current authoritative eligibility in atomic transactions."""
from decimal import Decimal
from pydantic import ValidationError
from app.core.authorization import lock_active_user, lock_verified_seller
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.models.product import ProductStatus
from app.repositories.catalog_repository import CatalogAuditRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.product_image_repository import ProductImageRepository
from app.schemas.product_image import PublicProductImage
from app.schemas.product import OwnProduct, OwnProductList, ProductCreate, PublicProduct, PublicSeller
from app.services.catalog_service import CategoryService, CityService
from app.services.profile_service import OnboardingIncompleteError, ProfileService


class ProductError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class ProductService:
    def __init__(self, repository=None, *, api_prefix="/api/v1"):
        self.repo = repository or ProductRepository()
        self.api_prefix = api_prefix

    @staticmethod
    def eligible(db, user_id):
        lock_verified_seller(db, user_id)
        try:
            ProfileService().get_completed_for_update(db, user_id)
        except OnboardingIncompleteError:
            raise ProductError("Complete marketplace onboarding before continuing.", 403) from None

    def owned(self, db, user_id, slug):
        row = self.repo.owned_for_update(db, user_id, slug)
        if row is None:
            raise ProductError("Listing not found.", 404)
        return row

    @staticmethod
    def fields(view):
        row, city, category, parent = view[:4]
        return dict(public_slug=row.public_slug, title=row.title, description=row.description,
                    price=format(row.price, ".2f"), currency=row.currency, condition=row.condition,
                    city=CityService.response(city), category=CategoryService.response(category, [parent] if parent else []),
                    published_at=row.published_at)

    @classmethod
    def own_response(cls, view):
        row, city, category, parent = view[:4]
        return OwnProduct(**cls.fields(view), status=row.status, city_active=city.is_active,
                          category_active=CategoryService.is_publicly_active(category, parent),
                          created_at=row.created_at, updated_at=row.updated_at)

    @retry_deadlock
    def create(self, db, user_id, body):
        with transaction(db):
            self.eligible(db, user_id)
            CatalogAuditRepository().lock_writes(db)
            city = CityService().resolve_active(db, body.city_slug)
            category = CategoryService().resolve_active(db, body.category_slug)
            row = self.repo.create(db, seller_user_id=user_id, title=body.title, description=body.description,
                                   price=Decimal(body.price), condition=body.condition, currency="CNY",
                                   city_id=city.id, category_id=category.id, status=ProductStatus.DRAFT)
            return self.own_response(self.repo.owned_view(db, user_id, row.public_slug))

    @retry_deadlock
    def list_owned(self, db, user_id, limit=20, offset=0):
        with transaction(db):
            lock_active_user(db, user_id)
            CatalogAuditRepository().lock_writes(db)
            views = self.repo.list_owned(db, user_id, limit, offset)
            return OwnProductList(items=[self.own_response(v) for v in views[:limit]],
                                  next_offset=offset + limit if len(views) > limit else None)

    @retry_deadlock
    def get_owned(self, db, user_id, slug):
        with transaction(db):
            lock_active_user(db, user_id)
            self.owned(db, user_id, slug)
            CatalogAuditRepository().lock_writes(db)
            return self.own_response(self.repo.owned_view(db, user_id, slug))

    @retry_deadlock
    def update(self, db, user_id, slug, body):
        with transaction(db):
            self.eligible(db, user_id)
            row = self.owned(db, user_id, slug)
            if row.status == ProductStatus.ARCHIVED:
                raise ProductError("Archived listings cannot be changed.")
            CatalogAuditRepository().lock_writes(db)
            if "city_slug" in body.model_fields_set:
                row.city_id = CityService().resolve_active(db, body.city_slug).id
            if "category_slug" in body.model_fields_set:
                row.category_id = CategoryService().resolve_active(db, body.category_slug).id
            for field in ("title", "description", "condition", "price"):
                if field in body.model_fields_set:
                    value = getattr(body, field)
                    setattr(row, field, Decimal(value) if field == "price" else value)
            db.flush()
            return self.own_response(self.repo.owned_view(db, user_id, slug))

    @retry_deadlock
    def transition(self, db, user_id, slug, action):
        with transaction(db):
            if action == "publish":
                self.eligible(db, user_id)
            else:
                lock_active_user(db, user_id)
            row = self.owned(db, user_id, slug)
            allowed = {"publish": (ProductStatus.DRAFT, ProductStatus.PAUSED),
                       "pause": (ProductStatus.PUBLISHED,),
                       "archive": (ProductStatus.DRAFT, ProductStatus.PUBLISHED, ProductStatus.PAUSED)}
            if action not in allowed or row.status not in allowed[action]:
                raise ProductError("Listing state does not allow this action.")
            if action == "publish":
                CatalogAuditRepository().lock_writes(db)
                view = self.repo.owned_view(db, user_id, slug)
                city = CityService().resolve_active(db, view[1].slug)
                category = CategoryService().resolve_active(db, view[2].slug)
                try:
                    ProductCreate(title=row.title, description=row.description, price=format(row.price, ".2f"),
                                  condition=row.condition, city_slug=city.slug, category_slug=category.slug)
                except ValidationError:
                    raise ProductError("Listing fields must be corrected before publishing.", 422) from None
                row.status = ProductStatus.PUBLISHED
                if row.published_at is None:
                    row.published_at = utc_now()
            else:
                row.status = ProductStatus.PAUSED if action == "pause" else ProductStatus.ARCHIVED
                CatalogAuditRepository().lock_writes(db)
            db.flush()
            return self.own_response(self.repo.owned_view(db, user_id, slug))

    def public_view(self, db, slug):
        view = self.repo.public_candidate(db, slug)
        if view is None:
            raise ProductError("Listing not found.", 404)
        return view

    def get_public(self, db, slug):
        view = self.public_view(db, slug)
        handle, display = view[7:9]
        images = [PublicProductImage(ref=image.public_ref, position=image.position,
            url=f"{self.api_prefix}/products/{slug}/images/{image.public_ref}")
            for image in ProductImageRepository().list_for_product(db, view[0].id)]
        return PublicProduct(**self.fields(view), status="PUBLISHED",
                             seller=PublicSeller(public_handle=handle, display_name=display, seller_verified=True),
                             images=images)
