from contextlib import contextmanager
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from app.core.database import get_db
from app.models.seller_verification import EvidenceType
from app.schemas.seller_verification import (
    StartOrSubmitRequest, VerificationResponse, EvidenceAccessRequest, SignedEvidenceResponse,
)
from app.services.seller_verification_service import VerificationError
from app.services.storage_service import UnsafeEvidence, sanitize_image, MAX_BYTES
from app.api.v1.seller_verification.dependencies import (
    get_seller_service, submission_user, upload_user, read_user,
)

router = APIRouter(tags=["seller-verification"])


@contextmanager
def safe_operation():
    try:
        yield
    except VerificationError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except UnsafeEvidence:
        raise HTTPException(422, "Invalid evidence or expired access.") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Verification operation unavailable. Please retry.") from None


@router.post("", response_model=VerificationResponse)
def start_or_submit(body: StartOrSubmitRequest, user=Depends(submission_user),
                    db: Session = Depends(get_db), service=Depends(get_seller_service)):
    with safe_operation():
        return service.start_or_submit(db, user.id, body.action)


@router.get("/me", response_model=VerificationResponse | None)
def get_mine(user=Depends(read_user), db: Session = Depends(get_db), service=Depends(get_seller_service)):
    with safe_operation():
        return service.own(db, user.id)


@router.post("/evidence", response_model=VerificationResponse, openapi_extra={
    "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
        "type": "object", "additionalProperties": False, "required": ["file", "evidence_type"],
        "properties": {"file": {"type": "string", "format": "binary"},
                       "evidence_type": {"type": "string", "enum": [e.value for e in EvidenceType]},
                       "challenge": {"type": "string", "pattern": "^[A-F0-9]{12}$",
                                     "description": "Required only for HANDWRITTEN_CODE; binds the upload to the current challenge."}},
    }}}},
})
async def upload_evidence(request: Request, user=Depends(upload_user),
                          db: Session = Depends(get_db), service=Depends(get_seller_service)):
    with safe_operation():
        try:
            async with request.form(max_files=1, max_fields=2, max_part_size=MAX_BYTES) as form:
                kind = EvidenceType(form.get("evidence_type"))
                expected = {"file", "evidence_type"}
                challenge = None
                if kind == EvidenceType.HANDWRITTEN_CODE:
                    expected.add("challenge")
                    challenge = form.get("challenge")
                    if not isinstance(challenge, str) or not re.fullmatch(r"[A-F0-9]{12}", challenge):
                        raise ValueError
                if set(form) != expected or len(form.multi_items()) != len(expected):
                    raise ValueError
                file = form["file"]
                if not isinstance(file, UploadFile):
                    raise ValueError
                data = await file.read(MAX_BYTES + 1)
                filename, mime_type = file.filename or "", file.content_type or ""
        except Exception:
            raise HTTPException(422, "Provide one evidence type and one JPEG or PNG image.") from None
        image = await run_in_threadpool(sanitize_image, data, filename, mime_type)
        return await run_in_threadpool(service.upload, db, user.id, kind, image, challenge)


@router.post("/evidence/access", response_model=SignedEvidenceResponse)
def evidence_access(body: EvidenceAccessRequest, request: Request, user=Depends(read_user),
                    db: Session = Depends(get_db), service=Depends(get_seller_service)):
    with safe_operation():
        key, _, _ = service.authorized_evidence(db, user.id, body.review_reference, body.evidence_type)
        return SignedEvidenceResponse(
            expires_in=60,
            url=f"{request.app.state.settings.api_v1_prefix}/seller-verification/evidence/content",
            ticket=service.storage.issue_download_ticket(
                key, actor_id=user.id, reference=body.review_reference,
                evidence_type=body.evidence_type.value))


@router.get("/evidence/content", response_class=Response)
def evidence_content(user=Depends(read_user), db: Session = Depends(get_db),
                     service=Depends(get_seller_service),
                     ticket: str = Header(alias="X-Evidence-Ticket", min_length=129, max_length=129,
                                          pattern=r"^[a-f0-9]{64}\.[a-f0-9]{64}$")):
    with safe_operation():
        data, mime = service.read_evidence(db, user.id, ticket)
        return Response(data, media_type=mime, headers={
            "Content-Disposition": 'attachment; filename="evidence.' + ("png" if mime == "image/png" else "jpg") + '"',
            "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox",
        })
