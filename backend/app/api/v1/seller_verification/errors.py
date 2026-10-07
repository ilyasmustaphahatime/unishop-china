"""HTTP-only error translation shared by seller and reviewer routes."""
from contextlib import contextmanager

from fastapi import HTTPException

from app.services.seller_verification_service import VerificationError
from app.services.storage_service import UnsafeEvidence


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
