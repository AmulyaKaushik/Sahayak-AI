"""Shared Redis handle for the security package (login rate-limit, session
ownership, refresh-token rotation)."""

from redis import Redis

from settings import settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client
