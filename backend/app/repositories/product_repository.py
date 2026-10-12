"""Bounded parameterized persistence. Services own authorization and commits."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from app.common.product_slugs import generate_product_slug
from app.models import Category, City, ProductListing, User, UserProfile
from app.repositories.seller_verification_repository import SellerVerificationRepository


class ProductRepository:
    @staticmethod
    def joined():
        parent = aliased(Category)
        return (select(ProductListing, City, Category, parent)
                .join(City, City.id == ProductListing.city_id)
                .join(Category, Category.id == ProductListing.category_id)
                .outerjoin(parent, parent.id == Category.parent_id))

    def create(self, db, **values):
        # Savepoint retries only the named unique-slug collision, not other DB
        # failures. Eligibility/catalog locks survive each bounded retry.
        for _ in range(8):
            try:
                with db.begin_nested():
                    row = ProductListing(public_slug=generate_product_slug(), **values)
                    db.add(row)
                    db.flush()
                return row
            except IntegrityError as exc:
                if getattr(exc.orig, "args", (None,))[0] != 1062 or "uq_product_listings_public_slug" not in str(exc.orig):
                    raise
        raise RuntimeError("Listing reference generation unavailable.")

    def owned_for_update(self, db, user_id, slug):
        return db.scalar(select(ProductListing).where(ProductListing.seller_user_id == user_id,
                         ProductListing.public_slug == slug).with_for_update().execution_options(populate_existing=True))

    def owned_view(self, db, user_id, slug):
        return db.execute(self.joined().where(ProductListing.seller_user_id == user_id,
                          ProductListing.public_slug == slug).with_for_update(read=True)
                          .execution_options(populate_existing=True)).first()

    def list_owned(self, db, user_id, limit, offset):
        return db.execute(self.joined().where(ProductListing.seller_user_id == user_id)
                          .order_by(ProductListing.updated_at.desc(), ProductListing.id.desc())
                          .limit(limit + 1).offset(offset).with_for_update(read=True)
                          .execution_options(populate_existing=True)).all()

    def public_candidate(self, db, slug):
        # One consistent visibility snapshot; no authentication PII is selected.
        return db.execute(self.joined().add_columns(
            User.account_status, User.email_verified, User.phone_verified,
            UserProfile.public_handle, UserProfile.display_name, UserProfile.onboarding_completed,
            UserProfile.city_id, SellerVerificationRepository.verified_predicate(User.id),
        ).join(User, User.id == ProductListing.seller_user_id)
          .join(UserProfile, UserProfile.user_id == User.id)
          .where(ProductListing.public_slug == slug)).first()
