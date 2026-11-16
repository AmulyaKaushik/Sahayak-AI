from fastapi import HTTPException

from security.redis_client import get_redis
from settings import settings


def check_login_rate_limit(login_id: str) -> None:
    """Fixed-window counter per login_id; raises 429 past the limit. Counts
    every attempt (successful or not) so it also caps registration spam."""
    key = f"login_attempts:{login_id}"
    redis = get_redis()
    attempts = redis.incr(key)
    if attempts == 1:
        redis.expire(key, settings.login_window_seconds)
    if attempts > settings.login_max_attempts:
        raise HTTPException(
            status_code=429, detail="Too many attempts. Please wait a minute and try again."
        )


def clear_login_attempts(login_id: str) -> None:
    get_redis().delete(f"login_attempts:{login_id}")
