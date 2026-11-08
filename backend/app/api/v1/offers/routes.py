"""Private negotiation transport; services commit before returning success."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.offer_dependencies import Actor, offer_query, safe_offer_operation
from app.core.database import get_db
from app.schemas.deal import DealResponse
from app.schemas.offer import CounterOffer, OfferCreate, OfferListQuery, OfferPage, OfferRef, OfferResponse, OFFER_ERRORS
from app.services.offer_service import OfferService

router = APIRouter(tags=["private offers"], responses=OFFER_ERRORS)


@router.post("", response_model=OfferResponse, status_code=201,
             responses={200: {"model": OfferResponse, "description": "Identical authorized replay."}},
             description="Buyer proposal for an existing conversation; immutable CNY decimal string; 24-hour expiry.")
def create(body: OfferCreate, request: Request, response: Response, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        result, created = OfferService(db, request.app.state.settings).create(actor, body)
        response.status_code = 201 if created else 200
        response.headers["Location"] = f"{request.app.state.settings.api_v1_prefix}/offers/{result.offer_ref}"
        return result


@router.get("", response_model=OfferPage, description="Participant-only keyset history; effective status filtering occurs before LIMIT.")
def list_offers(request: Request, actor: Actor, query: OfferListQuery = Depends(offer_query), db: Session = Depends(get_db)):
    with safe_offer_operation():
        return OfferService(db, request.app.state.settings).list(actor, query)


@router.get("/{offer_ref}", response_model=OfferResponse)
def get(offer_ref: OfferRef, request: Request, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        return OfferService(db, request.app.state.settings).get(actor, offer_ref)


@router.post("/{offer_ref}/counteroffers", response_model=OfferResponse, status_code=201,
             responses={200: {"model": OfferResponse, "description": "Identical authorized replay."}},
             description="Recipient creates a new immutable proposal and closes its parent atomically.")
def counter(offer_ref: OfferRef, body: CounterOffer, request: Request, response: Response, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        result, created = OfferService(db, request.app.state.settings).counter(actor, offer_ref, body)
        response.status_code = 201 if created else 200
        response.headers["Location"] = f"{request.app.state.settings.api_v1_prefix}/offers/{result.offer_ref}"
        return result


@router.post("/{offer_ref}/accept", response_model=DealResponse,
             description="Recipient accepts: one agreement, listing archival and competing proposal closure commit atomically. Bodyless; replay-safe.")
def accept(offer_ref: OfferRef, request: Request, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        return OfferService(db, request.app.state.settings).transition(actor, offer_ref, "accept")


@router.post("/{offer_ref}/reject", response_model=OfferResponse, description="Recipient rejects a pending offer. Bodyless; identical repeats are safe.")
def reject(offer_ref: OfferRef, request: Request, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        return OfferService(db, request.app.state.settings).transition(actor, offer_ref, "reject")


@router.post("/{offer_ref}/withdraw", response_model=OfferResponse, description="Proposer withdraws a pending offer. Bodyless; identical repeats are safe.")
def withdraw(offer_ref: OfferRef, request: Request, actor: Actor, db: Session = Depends(get_db)):
    with safe_offer_operation():
        return OfferService(db, request.app.state.settings).transition(actor, offer_ref, "withdraw")
