import logging
from contextlib import asynccontextmanager

import psycopg
import redis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from db_manager.me_api import router as me_router
from rag.api import router as admin_documents_router
from sahayak_ai.api import router as chat_router
from security.admin import require_admin
from security.api import router as auth_router
from settings import settings
from speech.api import router as speech_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_setup:
        from bootstrap import run_startup_tasks

        try:
            run_startup_tasks()
        except Exception:
            # Keep serving so /health works and the logs show what is wrong.
            logging.getLogger("sahayak.bootstrap").exception("startup setup failed")
    yield


app = FastAPI(title="Sahayak AI Kiosk Service", lifespan=lifespan)

# --- Public / authenticated API (see connect.md section 9) -----------------
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(chat_router)
app.include_router(speech_router)
app.include_router(admin_documents_router)

# --- Development-only routes -----------------------------------------------
# These take customer_id from the URL/body with no authentication and expose
# every customer's data, so they are mounted only when ENABLE_DEBUG_ROUTES=true.
if settings.enable_debug_routes:
    from db_manager.api import router as profiles_router
    from supervisor.api import router as session_context_router
    from supervisor.query_api import router as query_router

    app.include_router(profiles_router)
    app.include_router(session_context_router)
    app.include_router(query_router)


# --- Error shape: {"error": {"code", "message"}} ---------------------------
# "detail" is kept alongside it because FastAPI clients (the mobile app's
# describeError) already read that field.
_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    409: "conflict", 413: "too_large", 415: "unsupported_media", 422: "invalid_request",
    429: "rate_limited", 502: "upstream_error", 503: "unavailable",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": _CODES.get(exc.status_code, "error"), "message": message},
            "detail": message,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = f"{location}: {first.get('msg', 'invalid request')}" if location else "invalid request"
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": message}, "detail": message},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# The mobile app's api.ts pings this path; same payload as /health.
@app.get("/api/v1/health", include_in_schema=False)
def health_v1() -> dict:
    return {"status": "ok"}


def run_cli() -> None:
    """Chat with Sahayak AI in the terminal:  python main.py

    Talks to the same orchestrator the API uses (no HTTP, no login). Needs
    Postgres and Redis running (docker compose up -d postgres redis)."""
    import asyncio
    import sys
    import uuid

    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    for noisy in ("httpx", "LiteLLM", "litellm"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    from sahayak_ai.orchestrator import handle_message

    customer_id = "cli-user"  # facts persist between runs; /reset starts clean
    session_id = str(uuid.uuid4())
    language = "en-IN"
    help_text = (
        "Commands: /lang hi-IN (reply language), /new (new session, keeps facts), "
        "/reset (forget everything), /help, /quit"
    )

    print("Sahayak AI (terminal). Ask about loans, schemes or eligibility.")
    print(help_text + "\n")

    async def chat() -> None:
        nonlocal customer_id, session_id, language
        while True:
            try:
                text = (await asyncio.to_thread(input, "You: ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not text:
                continue
            command, _, argument = text.partition(" ")
            if command in ("/quit", "/exit"):
                return
            if command == "/help":
                print(help_text)
            elif command == "/lang":
                language = argument.strip() or "en-IN"
                print(f"Language set to {language}")
            elif command == "/new":
                session_id = str(uuid.uuid4())
                print("New session started (your saved facts are kept).")
            elif command == "/reset":
                customer_id, session_id = f"cli-{uuid.uuid4()}", str(uuid.uuid4())
                print("Cleared. Starting fresh.")
            else:
                try:
                    reply = await handle_message(customer_id, session_id, text, language)
                except Exception as exc:
                    print(f"Sahayak: Sorry, something went wrong ({type(exc).__name__}: {exc})\n")
                    continue
                print(f"Sahayak: {reply.display_text}")
                print()

    asyncio.run(chat())


@app.get("/health/deps", dependencies=[Depends(require_admin)])
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


if __name__ == "__main__":
    run_cli()
