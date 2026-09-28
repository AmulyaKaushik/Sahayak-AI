from redis import Redis

from schemas.models import ContextEntry
from settings import settings

_redis_client: Redis | None = None


def _client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class SessionContextStore:
    """Single writer of the session context store (Section 4.5, constraint #3).
    Only the supervisor should ever hold an instance of this class."""

    def __init__(self, redis_client: Redis | None = None):
        self._redis = redis_client or _client()

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session_context:{session_id}"

    def write(self, entry: ContextEntry) -> None:
        self._redis.rpush(self._key(entry.session_id), entry.model_dump_json())

    def read(self, session_id: str) -> list[ContextEntry]:
        raw_entries = self._redis.lrange(self._key(session_id), 0, -1)
        return [ContextEntry.model_validate_json(raw) for raw in raw_entries]


class ReadOnlyContextView:
    """Given to worker agents instead of a SessionContextStore. Deliberately
    has no write method at all -- there is no method on this class a worker
    could call to write to the session context store."""

    def __init__(self, store: SessionContextStore):
        self._store = store

    def read(self, session_id: str) -> list[ContextEntry]:
        return self._store.read(session_id)
