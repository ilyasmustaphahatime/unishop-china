class RegistrationConflictError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class VerificationCodeConfigurationError(RuntimeError):
    """Raised when phone-code hashing is requested without a safe secret."""
