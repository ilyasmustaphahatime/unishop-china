from typing import Annotated

from pydantic import AfterValidator, Field
from app.common.public_handles import normalize_public_handle

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.profiles.dependencies import (
    enforce_onboarding_rate_limit,
    enforce_profile_write_rate_limit,
    enforce_public_profile_rate_limit,
    get_profile_service,
)
from app.core.database import get_db
from app.schemas.profile import (
    OnboardingCompleteRequest,
    OwnProfileResponse,
    ProfileUpdateRequest,
    PublicProfileResponse,
)
from app.services.auth_service import SafeAuthenticatedUser
from app.services.profile_service import (
    OnboardingIncompleteError,
    ProfileService,
    ProfileUnavailableError,
)

router = APIRouter(tags=["profiles"])
public_router = APIRouter(tags=["profiles"])


@router.get("/me", response_model=OwnProfileResponse)
def get_own_profile(
    current_user: SafeAuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db),
    service: ProfileService = Depends(get_profile_service),
) -> OwnProfileResponse:
    try:
        result = service.get_or_create_own(session, user_id=current_user.id)
    except ProfileUnavailableError as exc:
        raise _unavailable_error() from exc
    except Exception as exc:
        raise _operation_error() from exc
    return OwnProfileResponse.model_validate(result, from_attributes=True)


@router.patch("/me", response_model=OwnProfileResponse)
def update_own_profile(
    request: ProfileUpdateRequest,
    current_user: SafeAuthenticatedUser = Depends(enforce_profile_write_rate_limit),
    session: Session = Depends(get_db),
    service: ProfileService = Depends(get_profile_service),
) -> OwnProfileResponse:
    try:
        result = service.update_own(
            session,
            user_id=current_user.id,
            request=request,
        )
    except ProfileUnavailableError as exc:
        raise _unavailable_error() from exc
    except Exception as exc:
        raise _operation_error() from exc
    return OwnProfileResponse.model_validate(result, from_attributes=True)


@router.post("/onboarding/complete", response_model=OwnProfileResponse)
def complete_onboarding(
    _: OnboardingCompleteRequest,
    current_user: SafeAuthenticatedUser = Depends(enforce_onboarding_rate_limit),
    session: Session = Depends(get_db),
    service: ProfileService = Depends(get_profile_service),
) -> OwnProfileResponse:
    try:
        result = service.complete_onboarding(session, user_id=current_user.id)
    except OnboardingIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PROFILE_INCOMPLETE",
                "message": "A display name and supported city are required.",
            },
        ) from exc
    except ProfileUnavailableError as exc:
        raise _unavailable_error() from exc
    except Exception as exc:
        raise _operation_error() from exc
    return OwnProfileResponse.model_validate(result, from_attributes=True)


@public_router.get("/by-handle/{handle}", response_model=PublicProfileResponse)
def get_public_profile(
    handle: Annotated[
        str,
        Field(min_length=3, max_length=30,
              pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,28}[A-Za-z0-9]$",
              description="Public ASCII handle; lowercased for lookup. Reserved names are rejected."),
        AfterValidator(normalize_public_handle),
    ],
    request: Request,
    _: None = Depends(enforce_public_profile_rate_limit),
    session: Session = Depends(get_db),
    service: ProfileService = Depends(get_profile_service),
) -> PublicProfileResponse:
    if b"%" in request.scope.get("raw_path", b""):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    try:
        result = service.get_public(session, public_handle=handle)
    except Exception as exc:
        raise _operation_error() from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return PublicProfileResponse.model_validate(result, from_attributes=True)


def _unavailable_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Profile unavailable.")


def _operation_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Profile operation could not be completed.",
    )
