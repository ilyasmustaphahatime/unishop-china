"""Explicit personal history; public GET endpoints remain read-only."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.me.dependencies import personal_query, personal_user, safe_personal_operation
from app.common.product_slugs import ProductSlug
from app.core.database import get_db
from app.schemas.product_personalization import PersonalListQuery, RecentlyViewedPage
from app.services.personalization_cursor import PersonalizationCursorCodec
from app.services.recently_viewed_service import RecentlyViewedService

router = APIRouter(tags=["recently-viewed"])


def _service(request):
    config = request.app.state.settings
    return RecentlyViewedService(codec=PersonalizationCursorCodec(config),
        api_prefix=config.api_v1_prefix, retention=config.personal_history_limit)


@router.get("", response_model=RecentlyViewedPage)
def list_recently_viewed(request: Request, user=Depends(personal_user),
                         query: PersonalListQuery = Depends(personal_query),
                         db: Session = Depends(get_db)):
    with safe_personal_operation():
        return _service(request).list(db, user.id, query)


@router.post("/{slug}", status_code=204)
def record_view(slug: ProductSlug, request: Request,
                user=Depends(personal_user), db: Session = Depends(get_db)):
    with safe_personal_operation():
        _service(request).record(db, user.id, slug)
    return Response(status_code=204)


@router.delete("/{slug}", status_code=204)
def remove_recent_view(slug: ProductSlug, request: Request,
                       user=Depends(personal_user), db: Session = Depends(get_db)):
    with safe_personal_operation():
        _service(request).remove(db, user.id, slug)
    return Response(status_code=204)


@router.delete("", status_code=204)
def clear_recently_viewed(request: Request, user=Depends(personal_user),
                          db: Session = Depends(get_db)):
    with safe_personal_operation():
        _service(request).clear(db, user.id)
    return Response(status_code=204)
