from typing import Annotated
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.seller_verification import VerificationResponse, ReviewRequest, RejectRequest
from app.api.v1.seller_verification.dependencies import require_admin, get_seller_service
from app.api.v1.seller_verification.routes import safe_operation

router = APIRouter(tags=["seller-verification-admin"])


@router.get("", response_model=list[VerificationResponse])
def pending(user=Depends(require_admin), db: Session = Depends(get_db),
            service=Depends(get_seller_service), offset: int = Query(default=0, ge=0, le=10000)):
    with safe_operation():
        return service.list_pending(db, user.id, offset)


@router.post("/{id}/approve", response_model=VerificationResponse)
def approve(id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$", description="Opaque review reference, not a database ID.")],
            body: ReviewRequest, user=Depends(require_admin), db: Session = Depends(get_db),
            service=Depends(get_seller_service)):
    with safe_operation():
        return service.review(db, user.id, id, None)


@router.post("/{id}/reject", response_model=VerificationResponse)
def reject(id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$", description="Opaque review reference, not a database ID.")],
           body: RejectRequest, user=Depends(require_admin), db: Session = Depends(get_db),
           service=Depends(get_seller_service)):
    with safe_operation():
        return service.review(db, user.id, id, body.rejection_reason)
