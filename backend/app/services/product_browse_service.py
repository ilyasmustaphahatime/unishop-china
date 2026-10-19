"""Anonymous browsing orchestration: validate cursor, query, serialize public cards."""
from app.repositories.product_browse_repository import ProductBrowseRepository
from app.schemas.product_browse import BrowseQuery, BrowseSort, ProductBrowsePage
from app.services.product_browse_cursor import BrowseCursorCodec, BrowsePosition
from app.services.product_card import serialize_product_card


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
        items = [serialize_product_card(row, self.api_prefix) for row in emitted]
        next_cursor = None
        if has_more:
            last = emitted[-1]
            sort_value = last.published_at if query.sort == BrowseSort.NEWEST else last.price
            next_cursor = self.codec.encode(query, BrowsePosition(sort_value, last.public_slug))
        return ProductBrowsePage(items=items, next_cursor=next_cursor, has_more=has_more)
