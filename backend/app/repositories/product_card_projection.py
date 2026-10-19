"""Canonical public-card projection shared by browse and private product lists."""
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models import Category, City, ProductImage, ProductListing, User, UserProfile
from app.repositories.product_visibility import publicly_visible


def public_product_card_statement(*, from_clause=None):
    """Select only public fields, applying eligibility before any caller's LIMIT."""
    parent = aliased(Category)
    cover_ref = (
        select(ProductImage.public_ref)
        .where(ProductImage.product_listing_id == ProductListing.id)
        .order_by(ProductImage.position.asc()).limit(1)
        .correlate(ProductListing).scalar_subquery()
    )
    return (
        select(
            ProductListing.public_slug.label("public_slug"),
            ProductListing.title.label("title"),
            ProductListing.price.label("price"),
            ProductListing.currency.label("currency"),
            ProductListing.condition.label("condition"),
            ProductListing.published_at.label("published_at"),
            City.slug.label("city_slug"), City.name_en.label("city_name_en"),
            City.name_zh.label("city_name_zh"), City.province_en.label("city_province_en"),
            City.province_zh.label("city_province_zh"), City.country_code.label("country_code"),
            Category.slug.label("category_slug"), Category.name_en.label("category_name_en"),
            Category.name_zh.label("category_name_zh"),
            Category.description.label("category_description"),
            parent.slug.label("parent_slug"),
            UserProfile.public_handle.label("seller_handle"),
            UserProfile.display_name.label("seller_display_name"),
            cover_ref.label("cover_ref"),
        )
        .select_from(ProductListing if from_clause is None else from_clause)
        .join(City, City.id == ProductListing.city_id)
        .join(Category, Category.id == ProductListing.category_id)
        .outerjoin(parent, parent.id == Category.parent_id)
        .join(User, User.id == ProductListing.seller_user_id)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(publicly_visible(parent))
    )


def public_product_identity_statement():
    """Use exactly the same eligibility joins for private relationship writes/lookup."""
    return public_product_card_statement().with_only_columns(
        ProductListing.id, ProductListing.public_slug, maintain_column_froms=True,
    )
