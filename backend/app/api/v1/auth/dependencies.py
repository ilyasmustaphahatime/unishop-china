from app.core.config import settings
from app.services.auth_service import RegistrationService


def get_registration_service() -> RegistrationService:
    return RegistrationService(
        verification_code_hash_secret=settings.verification_code_hash_secret,
    )
