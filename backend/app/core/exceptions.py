class RegistrationConflictError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class VerificationCodeConfigurationError(RuntimeError):
    """Raised when phone-code hashing is requested without a safe secret."""


class PhoneVerificationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


class InvalidCredentialsError(Exception):
    """Internal generic authentication failure safe for public mapping."""


class TokenValidationError(Exception):
    """Internal access-token validation failure safe for public mapping."""
