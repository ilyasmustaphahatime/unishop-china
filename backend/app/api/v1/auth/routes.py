from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import get_registration_service
from app.core.database import get_db
from app.core.exceptions import (
    RegistrationConflictError,
    VerificationCodeConfigurationError,
)
from app.schemas.auth import RegisterRequest, RegisterResponse
from app.services.auth_service import RegistrationService

router = APIRouter(tags=["authentication"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    request: RegisterRequest,
    session: Session = Depends(get_db),
    service: RegistrationService = Depends(get_registration_service),
) -> RegisterResponse:
    try:
        result = service.register(session, request)
    except RegistrationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except VerificationCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "REGISTRATION_UNAVAILABLE",
                "message": "Phone registration is temporarily unavailable.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "REGISTRATION_FAILED",
                "message": "Registration could not be completed.",
            },
        ) from exc

    return RegisterResponse.model_validate(result, from_attributes=True)
