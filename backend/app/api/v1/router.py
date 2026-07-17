from fastapi import APIRouter, Response, status

from app.api.v1.auth.routes import router as auth_router
from app.core.database import check_database_connection

router = APIRouter()
router.include_router(auth_router, prefix="/auth")


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"application": "UniShop China API", "status": "running", "version": "1.0.0"}


@router.get("/health/database", tags=["health"])
def database_health(response: Response) -> dict[str, str | bool]:
    """Return database availability without exposing connection details."""
    if not check_database_connection():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"database": "mysql", "status": "unavailable", "connected": False}

    return {"database": "mysql", "status": "healthy", "connected": True}
