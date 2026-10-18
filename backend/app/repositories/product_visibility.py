"""The single SQL predicate for anonymous listing/detail/media visibility."""
from sqlalchemy import and_, func, or_

from app.common.enums import AccountStatus
from app.models import Category, City, ProductListing, User, UserProfile
from app.models.product import ProductStatus
from app.repositories.seller_verification_repository import SellerVerificationRepository


def publicly_visible(parent: Category):
    """Call only after joining listing, seller, profile, city, category and parent.

    Keeping this in the query also prevents hidden rows from affecting page size
    or continuation cursors. The profile field check mirrors onboarding's
    required_onboarding_fields_valid rule.
    """
    return and_(
        ProductListing.status == ProductStatus.PUBLISHED,
        ProductListing.published_at.is_not(None),
        User.account_status == AccountStatus.ACTIVE,
        User.email_verified.is_(True),
        User.phone_verified.is_(True),
        SellerVerificationRepository.verified_predicate(User.id),
        UserProfile.onboarding_completed.is_(True),
        UserProfile.display_name.is_not(None),
        func.char_length(UserProfile.display_name).between(2, 50),
        UserProfile.city_id.is_not(None),
        City.is_active.is_(True),
        Category.is_active.is_(True),
        or_(Category.parent_id.is_(None), and_(parent.is_active.is_(True), parent.level == 1)),
    )
