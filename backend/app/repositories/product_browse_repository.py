"""Single bounded public projection query; never materializes private ORM graphs."""
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import aliased

from app.models import Category, City, ProductListing
from app.repositories.product_card_projection import public_product_card_statement
from app.schemas.product_browse import BrowseQuery, BrowseSort
from app.services.product_browse_cursor import BrowsePosition


def browse_index(query: BrowseQuery) -> str:
    if query.q is not None:
        return "ix_product_listings_search_ngram"
    suffix = "newest" if query.sort == BrowseSort.NEWEST else "price"
    if query.category is not None:
        return f"ix_product_listings_category_{suffix}"
    if query.city is not None:
        return f"ix_product_listings_city_{suffix}"
    return f"ix_product_listings_browse_{suffix}"


class ProductBrowseRepository:
    def page_statement(self, query: BrowseQuery, position: BrowsePosition | None):
        stmt = (public_product_card_statement()
         # Public eligibility is evaluated after an indexed product read. Driving
         # from tiny catalog/seller tables caused unbounded filesorts in the
         # measured 20k-row workload, including keyword searches.
         .prefix_with("STRAIGHT_JOIN", dialect="mysql"))

        if query.q is not None:
            # The API normalizer permits only Unicode word characters/spaces;
            # '+' is introduced here, never accepted from the client. MySQL's
            # ngram boolean mode treats each word as a contiguous ngram phrase.
            terms = " ".join("+" + word for word in query.q.split())
            stmt = stmt.where(match(ProductListing.title, ProductListing.description,
                                    against=terms, in_boolean_mode=True))
        if query.city is not None:
            lookup_city = aliased(City)
            stmt = stmt.where(ProductListing.city_id == select(lookup_city.id).where(
                lookup_city.slug == query.city).scalar_subquery())
        if query.category is not None:
            lookup_category = aliased(Category)
            stmt = stmt.where(ProductListing.category_id == select(lookup_category.id).where(
                lookup_category.slug == query.category).scalar_subquery())
        if query.min_price is not None:
            stmt = stmt.where(ProductListing.price >= query.min_price)
        if query.max_price is not None:
            stmt = stmt.where(ProductListing.price <= query.max_price)
        if query.condition is not None:
            stmt = stmt.where(ProductListing.condition == query.condition.value)

        if query.sort == BrowseSort.NEWEST:
            sort_column = ProductListing.published_at
            ascending = False
        else:
            sort_column = ProductListing.price
            ascending = query.sort == BrowseSort.PRICE_ASC

        index = browse_index(query)
        stmt = stmt.with_hint(ProductListing, f"FORCE INDEX ({index})", dialect_name="mysql")

        if position is not None:
            compare = sort_column > position.value if ascending else sort_column < position.value
            tie_compare = (ProductListing.public_slug > position.slug if ascending
                           else ProductListing.public_slug < position.slug)
            stmt = stmt.where(or_(compare, and_(sort_column == position.value, tie_compare)))

        stmt = stmt.order_by(sort_column.asc() if ascending else sort_column.desc(),
                             ProductListing.public_slug.asc() if ascending else ProductListing.public_slug.desc())
        return stmt.limit(query.limit + 1)

    def page(self, db, query: BrowseQuery, position: BrowsePosition | None):
        return db.execute(self.page_statement(query, position)).mappings().all()
