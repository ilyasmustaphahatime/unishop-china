"""One safe public-card serializer for browse and authenticated personal lists."""
from app.schemas.catalog import PublicCategory, PublicCity
from app.schemas.product import PublicSeller
from app.schemas.product_browse import ProductCard, ProductCover


def serialize_product_card(row, api_prefix: str) -> ProductCard:
    city = PublicCity(slug=row.city_slug, name_en=row.city_name_en,
                      name_zh=row.city_name_zh, province_en=row.city_province_en,
                      province_zh=row.city_province_zh, country_code=row.country_code)
    category = PublicCategory(slug=row.category_slug, name_en=row.category_name_en,
                              name_zh=row.category_name_zh,
                              description=row.category_description, parent_slug=row.parent_slug)
    cover = (ProductCover(ref=row.cover_ref,
             url=f"{api_prefix}/products/{row.public_slug}/images/{row.cover_ref}")
             if row.cover_ref else None)
    return ProductCard(
        public_slug=row.public_slug, title=row.title, price=format(row.price, ".2f"),
        currency=row.currency, condition=row.condition, city=city, category=category,
        cover_image=cover, seller=PublicSeller(public_handle=row.seller_handle,
        display_name=row.seller_display_name, seller_verified=True),
        published_at=row.published_at.isoformat(),
    )
