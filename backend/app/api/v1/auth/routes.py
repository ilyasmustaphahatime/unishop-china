from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    enforce_auth_origin,
    enforce_email_verification_resend_rate_limit,
    enforce_email_verification_verify_rate_limit,
    enforce_forgot_password_rate_limit,
    enforce_login_rate_limit,
    enforce_logout_all_rate_limit,
    enforce_logout_rate_limit,
    enforce_password_change_rate_limit,
    enforce_password_reset_rate_limit,
    enforce_refresh_rate_limit,
    enforce_registration_rate_limit,
    get_authentication_service,
    get_current_user,
    get_email_verification_service,
    get_phone_verification_service,
    get_password_change_service,
    get_password_reset_completion_service,
    get_password_reset_service,
    get_refresh_session_service,
    get_registration_service,
)
from app.core.database import get_db
from app.core.auth_cookies import clear_auth_cookies, set_auth_cookies
from app.core.config import settings
from app.core.exceptions import (
    InvalidCredentialsError,
    EmailVerificationError,
    InvalidPasswordChangeError,
    InvalidPasswordResetError,
    RequestVerificationError,
    RegistrationConflictError,
    SessionRefreshError,
    PhoneVerificationError,
    VerificationCodeConfigurationError,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RegisterRequest,
    RegisterResponse,
    ResendPhoneVerificationCodeRequest,
    ResendPhoneVerificationCodeResponse,
    ResendEmailVerificationCodeRequest,
    ResendEmailVerificationCodeResponse,
    SafeAuthenticatedUserResponse,
    VerifyPhoneCodeRequest,
    VerifyPhoneCodeResponse,
    VerifyEmailCodeRequest,
    VerifyEmailCodeResponse,
)
from app.services.auth_service import AuthenticationService, RegistrationService, SafeAuthenticatedUser
from app.services.email_verification_service import EmailVerificationService
from app.services.password_reset_service import (
    GENERIC_INVALID_PASSWORD_RESET_MESSAGE,
    GENERIC_FORGOT_PASSWORD_MESSAGE,
    PASSWORD_RESET_SUCCESS_MESSAGE,
    PasswordResetCompletionService,
    PasswordResetRequestService,
)
from app.services.password_change_service import (
    GENERIC_INVALID_PASSWORD_CHANGE_MESSAGE,
    PASSWORD_CHANGE_SUCCESS_MESSAGE,
    PasswordChangeService,
)
from app.services.phone_verification_service import PhoneVerificationService
from app.services.refresh_session_service import RefreshSessionService

router = APIRouter(tags=["authentication"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.post(
    "/email/resend-code",
    response_model=ResendEmailVerificationCodeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_email_verification_code(
    request: ResendEmailVerificationCodeRequest,
    response: Response,
    _: None = Depends(enforce_auth_origin),
    current_user: SafeAuthenticatedUser = Depends(
        enforce_email_verification_resend_rate_limit
    ),
    session: Session = Depends(get_db),
    service: EmailVerificationService = Depends(get_email_verification_service),
) -> ResendEmailVerificationCodeResponse:
    try:
        result = service.resend(session, user_id=current_user.id)
    except EmailVerificationError as exc:
        headers = dict(NO_STORE_HEADERS)
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers=headers,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification request could not be completed.",
            headers=NO_STORE_HEADERS,
        ) from exc
    response.headers.update(NO_STORE_HEADERS)
    return ResendEmailVerificationCodeResponse.model_validate(
        result,
        from_attributes=True,
    )


@router.post(
    "/email/verify",
    response_model=VerifyEmailCodeResponse,
    status_code=status.HTTP_200_OK,
)
def verify_email_code(
    request: VerifyEmailCodeRequest,
    response: Response,
    _: None = Depends(enforce_auth_origin),
    current_user: SafeAuthenticatedUser = Depends(
        enforce_email_verification_verify_rate_limit
    ),
    session: Session = Depends(get_db),
    service: EmailVerificationService = Depends(get_email_verification_service),
) -> VerifyEmailCodeResponse:
    try:
        result = service.verify(
            session,
            user_id=current_user.id,
            submitted_code=request.code,
        )
    except EmailVerificationError as exc:
        headers = dict(NO_STORE_HEADERS)
        if exc.retry_after is not None:
            headers["Retry-After"] = str(exc.retry_after)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers=headers,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification could not be completed.",
            headers=NO_STORE_HEADERS,
        ) from exc
    response.headers.update(NO_STORE_HEADERS)
    return VerifyEmailCodeResponse.model_validate(result, from_attributes=True)


@router.post(
    "/password/forgot",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    response: Response,
    _: None = Depends(enforce_auth_origin),
    request: ForgotPasswordRequest = Depends(enforce_forgot_password_rate_limit),
    session: Session = Depends(get_db),
    service: PasswordResetRequestService = Depends(get_password_reset_service),
) -> ForgotPasswordResponse:
    try:
        service.request_reset(
            session,
            identifier=request.identifier,
            identifier_kind=request.identifier_kind,
        )
    except Exception:
        pass
    response.headers.update(NO_STORE_HEADERS)
    return ForgotPasswordResponse(message=GENERIC_FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/password/reset",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
)
def reset_password(
    response: Response,
    _: None = Depends(enforce_auth_origin),
    request: ResetPasswordRequest = Depends(enforce_password_reset_rate_limit),
    session: Session = Depends(get_db),
    service: PasswordResetCompletionService = Depends(
        get_password_reset_completion_service
    ),
) -> ResetPasswordResponse:
    try:
        service.reset_password(
            session,
            identifier=request.identifier,
            identifier_kind=request.identifier_kind,
            code=request.code,
            new_password=request.new_password,
        )
    except InvalidPasswordResetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=GENERIC_INVALID_PASSWORD_RESET_MESSAGE,
            headers=NO_STORE_HEADERS,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset could not be completed.",
            headers=NO_STORE_HEADERS,
        ) from exc
    response.headers.update(NO_STORE_HEADERS)
    return ResetPasswordResponse(message=PASSWORD_RESET_SUCCESS_MESSAGE)


@router.post(
    "/password/change",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
)
def change_password(
    request: ChangePasswordRequest,
    response: Response,
    _: None = Depends(enforce_auth_origin),
    current_user: SafeAuthenticatedUser = Depends(
        enforce_password_change_rate_limit
    ),
    session: Session = Depends(get_db),
    service: PasswordChangeService = Depends(get_password_change_service),
) -> ChangePasswordResponse:
    try:
        service.change_password(
            session,
            user_id=current_user.id,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except InvalidPasswordChangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=GENERIC_INVALID_PASSWORD_CHANGE_MESSAGE,
            headers=NO_STORE_HEADERS,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change could not be completed.",
            headers=NO_STORE_HEADERS,
        ) from exc
    clear_auth_cookies(response, settings)
    response.headers.update(NO_STORE_HEADERS)
    return ChangePasswordResponse(message=PASSWORD_CHANGE_SUCCESS_MESSAGE)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    response: Response,
    request: LoginRequest = Depends(enforce_login_rate_limit),
    _: None = Depends(enforce_auth_origin),
    session: Session = Depends(get_db),
    service: AuthenticationService = Depends(get_authentication_service),
) -> LoginResponse:
    try:
        result = service.authenticate_user_and_create_access_token(session, request)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer", **NO_STORE_HEADERS},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login could not be completed.",
            headers=NO_STORE_HEADERS,
        ) from exc
    set_auth_cookies(
        response,
        refresh_token=result.cookies.refresh_token,
        csrf_token=result.cookies.csrf_token,
        max_age=result.cookies.max_age,
        config=settings,
    )
    response.headers.update(NO_STORE_HEADERS)
    return LoginResponse.model_validate(result, from_attributes=True)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_session(
    request: Request,
    response: Response,
    _: None = Depends(enforce_auth_origin),
    __: None = Depends(enforce_refresh_rate_limit),
    session: Session = Depends(get_db),
    service: RefreshSessionService = Depends(get_refresh_session_service),
) -> RefreshResponse | Response:
    try:
        result = service.rotate_session(
            session,
            raw_refresh_token=request.cookies.get(settings.refresh_cookie_name) or "",
            csrf_cookie=request.cookies.get(settings.csrf_cookie_name),
            csrf_header=request.headers.get("x-csrf-token"),
        )
    except RequestVerificationError:
        return _session_error_response(
            status.HTTP_403_FORBIDDEN,
            "Request verification failed.",
            clear_cookies=False,
        )
    except SessionRefreshError:
        return _session_error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Could not refresh session.",
            clear_cookies=True,
        )
    except Exception:
        return _session_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Session refresh could not be completed.",
            clear_cookies=False,
        )

    set_auth_cookies(
        response,
        refresh_token=result.cookies.refresh_token,
        csrf_token=result.cookies.csrf_token,
        max_age=result.cookies.max_age,
        config=settings,
    )
    response.headers.update(NO_STORE_HEADERS)
    return RefreshResponse.model_validate(result, from_attributes=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    _: None = Depends(enforce_auth_origin),
    __: None = Depends(enforce_logout_rate_limit),
    session: Session = Depends(get_db),
    service: RefreshSessionService = Depends(get_refresh_session_service),
) -> Response:
    try:
        service.logout_current(
            session,
            raw_refresh_token=request.cookies.get(settings.refresh_cookie_name),
            csrf_cookie=request.cookies.get(settings.csrf_cookie_name),
            csrf_header=request.headers.get("x-csrf-token"),
        )
    except RequestVerificationError:
        return _session_error_response(
            status.HTTP_403_FORBIDDEN,
            "Request verification failed.",
            clear_cookies=False,
        )
    except Exception:
        return _session_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Logout could not be completed.",
            clear_cookies=False,
        )
    clear_auth_cookies(response, settings)
    response.headers.update(NO_STORE_HEADERS)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response,
    _: None = Depends(enforce_auth_origin),
    current_user: SafeAuthenticatedUser = Depends(enforce_logout_all_rate_limit),
    session: Session = Depends(get_db),
    service: RefreshSessionService = Depends(get_refresh_session_service),
) -> Response:
    try:
        service.logout_all(session, user_id=current_user.id)
    except Exception:
        return _session_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Logout could not be completed.",
            clear_cookies=False,
        )
    clear_auth_cookies(response, settings)
    response.headers.update(NO_STORE_HEADERS)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _session_error_response(
    status_code: int,
    detail: str,
    *,
    clear_cookies: bool,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=NO_STORE_HEADERS,
    )
    if clear_cookies:
        clear_auth_cookies(response, settings)
    return response


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
