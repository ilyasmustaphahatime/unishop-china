"""Current-user favorites; client input never supplies an owner identity."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.me.dependencies import personal_query, personal_user, safe_personal_operation
from app.common.product_slugs import ProductSlug
from app.core.database import get_db
from app.schemas.product_personalization import (
    FavoriteLookupRequest, FavoriteStatus, FavoritesLookupResponse, FavoritesPage, PersonalListQuery,
)
from app.services.favorites_service import FavoritesService
from app.services.personalization_cursor import PersonalizationCursorCodec

router = APIRouter(tags=["favorites"])


def _service(request):
    config = request.app.state.settings
    return FavoritesService(codec=PersonalizationCursorCodec(config),
                            api_prefix=config.api_v1_prefix, quota=config.personal_favorites_limit)


@router.get("", response_model=FavoritesPage)
def list_favorites(request: Request, user=Depends(personal_user),
                   query: PersonalListQuery = Depends(personal_query), db: Session = Depends(get_db)):
    with safe_personal_operation():
        return _service(request).list(db, user.id, query)


@router.post("/lookup", response_model=FavoritesLookupResponse)
def lookup_favorites(body: FavoriteLookupRequest, request: Request,
                     user=Depends(personal_user), db: Session = Depends(get_db)):
    with safe_personal_operation():
        return _service(request).lookup(db, user.id, body.product_slugs)


@router.put("/{slug}", response_model=FavoriteStatus)
def add_favorite(slug: ProductSlug, request: Request,
                 user=Depends(personal_user), db: Session = Depends(get_db)):
    with safe_personal_operation():
        return _service(request).add(db, user.id, slug)


@router.delete("/{slug}", status_code=204)
def remove_favorite(slug: ProductSlug, request: Request,
                    user=Depends(personal_user), db: Session = Depends(get_db)):
    with safe_personal_operation():
        _service(request).remove(db, user.id, slug)
    return Response(status_code=204)
