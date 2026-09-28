import psycopg
import redis
from fastapi import FastAPI

from db_manager.api import router as profiles_router
from settings import settings
from supervisor.api import router as session_context_router
from supervisor.query_api import router as query_router

app = FastAPI(title="Sahayak AI Kiosk Service")
app.include_router(profiles_router)
app.include_router(session_context_router)
app.include_router(query_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/deps")
def health_deps() -> dict:
    deps = {"postgres": "unknown", "redis": "unknown"}

    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        deps["postgres"] = "ok"
    except Exception as exc:
        deps["postgres"] = f"error: {exc}"

    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        deps["redis"] = "ok"
    except Exception as exc:
        deps["redis"] = f"error: {exc}"

    return deps
