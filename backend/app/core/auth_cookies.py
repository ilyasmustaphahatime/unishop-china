from fastapi import Response

from app.core.config import Settings, settings


def set_auth_cookies(
    response: Response,
    *,
    refresh_token: str,
    csrf_token: str,
    max_age: int,
    config: Settings = settings,
) -> None:
    cookie_options = {
        "secure": config.refresh_cookie_secure,
        "samesite": config.refresh_cookie_samesite.lower(),
        "path": config.refresh_cookie_path,
        "max_age": max_age,
        "expires": max_age,
    }
    response.set_cookie(
        config.refresh_cookie_name,
        refresh_token,
        httponly=True,
        **cookie_options,
    )
    response.set_cookie(
        config.csrf_cookie_name,
        csrf_token,
        httponly=False,
        **cookie_options,
    )


def clear_auth_cookies(response: Response, config: Settings = settings) -> None:
    common = {
        "path": config.refresh_cookie_path,
        "secure": config.refresh_cookie_secure,
        "samesite": config.refresh_cookie_samesite.lower(),
    }
    response.delete_cookie(config.refresh_cookie_name, httponly=True, **common)
    response.delete_cookie(config.csrf_cookie_name, httponly=False, **common)
