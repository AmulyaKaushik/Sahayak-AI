import hmac

from fastapi import Header, HTTPException

from settings import settings


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Guards /api/v1/admin/*. Disabled entirely (403) when ADMIN_API_KEY is
    not configured, so a forgotten env var can't leave uploads open."""
    if not settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Admin API is not enabled")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")
