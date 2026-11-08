"""Read-only agreements; no fulfillment or payment endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.api.offer_dependencies import Actor, deal_query, safe_offer_operation
from app.core.database import get_db
from app.schemas.deal import DealPage, DealResponse
from app.schemas.offer import DealListQuery, DealRef, OFFER_ERRORS
from app.services.deal_service import DealService

router = APIRouter(tags=["private deals"], responses=OFFER_ERRORS)


@router.get("", response_model=DealPage, description="Only agreements in the authenticated participant's conversations.")
def list_deals(request: Request, actor: Actor, query: DealListQuery = Depends(deal_query), db: Session = Depends(get_db)):
    with safe_offer_operation():
        return DealService(db, request.app.state.settings).list(actor, query)


@router.get("/{deal_ref}", response_model=DealResponse, description="An agreement records accepted terms, not payment or completed ownership transfer.")
def get(deal_ref: DealRef, request: Request, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        return DealService(db, request.app.state.settings).get(actor, deal_ref)
