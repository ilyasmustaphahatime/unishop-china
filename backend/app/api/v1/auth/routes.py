from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    enforce_login_rate_limit,
    enforce_registration_rate_limit,
    get_authentication_service,
    get_current_user,
    get_phone_verification_service,
    get_registration_service,
)
from app.core.database import get_db
from app.core.exceptions import (
    InvalidCredentialsError,
    RegistrationConflictError,
    PhoneVerificationError,
    VerificationCodeConfigurationError,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResendPhoneVerificationCodeRequest,
    ResendPhoneVerificationCodeResponse,
    SafeAuthenticatedUserResponse,
    VerifyPhoneCodeRequest,
    VerifyPhoneCodeResponse,
)
from app.services.auth_service import AuthenticationService, RegistrationService, SafeAuthenticatedUser
from app.services.phone_verification_service import PhoneVerificationService

router = APIRouter(tags=["authentication"])


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    request: LoginRequest = Depends(enforce_login_rate_limit),
    session: Session = Depends(get_db),
    service: AuthenticationService = Depends(get_authentication_service),
) -> LoginResponse:
    try:
        result = service.authenticate_user_and_create_access_token(session, request)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login could not be completed.",
        ) from exc
    return LoginResponse.model_validate(result, from_attributes=True)


@router.get(
    "/me",
    response_model=SafeAuthenticatedUserResponse,
    status_code=status.HTTP_200_OK,
)
def get_me(
    current_user: SafeAuthenticatedUser = Depends(get_current_user),
) -> SafeAuthenticatedUserResponse:
    return SafeAuthenticatedUserResponse.model_validate(current_user)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    request: RegisterRequest,
    _: None = Depends(enforce_registration_rate_limit),
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


@router.post(
    "/phone/resend-code",
    response_model=ResendPhoneVerificationCodeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_phone_verification_code(
    request: ResendPhoneVerificationCodeRequest,
    response: Response,
    session: Session = Depends(get_db),
    service: PhoneVerificationService = Depends(get_phone_verification_service),
) -> ResendPhoneVerificationCodeResponse:
    try:
        result = service.resend(session, request.phone_number)
    except PhoneVerificationError as exc:
        if exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers=dict(response.headers),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "VERIFICATION_FAILED", "message": "Request could not be completed."},
        ) from exc
    return ResendPhoneVerificationCodeResponse.model_validate(result, from_attributes=True)


@router.post(
    "/phone/verify",
    response_model=VerifyPhoneCodeResponse,
    status_code=status.HTTP_200_OK,
)
def verify_phone_code(
    request: VerifyPhoneCodeRequest,
    session: Session = Depends(get_db),
    service: PhoneVerificationService = Depends(get_phone_verification_service),
) -> VerifyPhoneCodeResponse:
    try:
        result = service.verify(session, request.phone_number, request.code)
    except PhoneVerificationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "VERIFICATION_FAILED", "message": "Request could not be completed."},
        ) from exc
    return VerifyPhoneCodeResponse.model_validate(result, from_attributes=True)
