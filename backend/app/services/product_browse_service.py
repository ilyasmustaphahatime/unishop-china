"""Anonymous browsing orchestration: validate cursor, query, serialize public cards."""
from app.repositories.product_browse_repository import ProductBrowseRepository
from app.schemas.catalog import PublicCategory, PublicCity
from app.schemas.product import PublicSeller
from app.schemas.product_browse import BrowseQuery, BrowseSort, ProductBrowsePage, ProductCard, ProductCover
from app.services.product_browse_cursor import BrowseCursorCodec, BrowsePosition


class ProductBrowseService:
    def __init__(self, *, codec: BrowseCursorCodec, api_prefix: str,
                 repository: ProductBrowseRepository | None = None):
        self.codec = codec
        self.api_prefix = api_prefix
        self.repo = repository or ProductBrowseRepository()

    def browse(self, db, query: BrowseQuery) -> ProductBrowsePage:
        position = self.codec.decode(query.cursor, query) if query.cursor is not None else None
        rows = self.repo.page(db, query, position)
        has_more = len(rows) > query.limit
        emitted = rows[:query.limit]
        items = []
        for row in emitted:
            city = PublicCity(slug=row.city_slug, name_en=row.city_name_en,
                              name_zh=row.city_name_zh, province_en=row.city_province_en,
                              province_zh=row.city_province_zh, country_code=row.country_code)
            category = PublicCategory(slug=row.category_slug, name_en=row.category_name_en,
                                      name_zh=row.category_name_zh,
                                      description=row.category_description, parent_slug=row.parent_slug)
            cover = (ProductCover(ref=row.cover_ref,
                     url=f"{self.api_prefix}/products/{row.public_slug}/images/{row.cover_ref}")
                     if row.cover_ref else None)
            items.append(ProductCard(
                public_slug=row.public_slug, title=row.title, price=format(row.price, ".2f"),
                currency=row.currency, condition=row.condition, city=city, category=category,
                cover_image=cover, seller=PublicSeller(public_handle=row.seller_handle,
                display_name=row.seller_display_name, seller_verified=True),
                published_at=row.published_at.isoformat(),
            ))
        next_cursor = None
        if has_more:
            last = emitted[-1]
            sort_value = last.published_at if query.sort == BrowseSort.NEWEST else last.price
            next_cursor = self.codec.encode(query, BrowsePosition(sort_value, last.public_slug))
        return ProductBrowsePage(items=items, next_cursor=next_cursor, has_more=has_more)
