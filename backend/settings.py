from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://sahayak:sahayak@localhost:5432/sahayak"
    redis_url: str = "redis://localhost:6379/0"

    # LLM provider for worker agent field extraction + narration (Section 6
    # says "Anthropic + fallback"; swapped to Groq at the user's explicit
    # request -- DSPy's provider-agnostic LM abstraction makes this a
    # one-line change, not a structural one).
    groq_api_key: str | None = None
    # More keys, comma separated. Calls rotate round-robin over all keys
    # (this one and GROQ_API_KEY), which multiplies the free-tier limit.
    groq_api_keys: str | None = None
    worker_llm_model: str = "groq/openai/gpt-oss-120b"
    # Small, fast model for the cheap decisions (routing, classification,
    # rewording). Groq counts the free-tier token limit per model, so using a
    # second model also doubles the budget.
    fast_llm_model: str = "groq/openai/gpt-oss-20b"
    # How long the gpt-oss models "think" before answering; "low" cuts tokens
    # and latency a lot for these simple tasks. Empty/None = provider default.
    llm_reasoning_effort: str | None = "low"

    # --- Auth (connect.md section 3) -------------------------------------
    # No default on purpose: the app refuses to start without a secret.
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    login_max_attempts: int = 5  # per login_id, per login_window_seconds
    login_window_seconds: int = 60
    session_ttl_seconds: int = 86400

    # Protects /api/v1/admin/* (document upload / review).
    admin_api_key: str | None = None

    # The pre-auth routes that take customer_id from the request body
    # (/profiles/*, /session-context/*, /api/v1/query, /health/deps) expose
    # every customer's data. They stay available for local development and
    # the existing test-suite, but must be OFF in any cloud deployment.
    enable_debug_routes: bool = False

    # Run migrations, seed missing eligibility rules and sync the documents
    # folder on every start. Turn on for a fresh cloud deployment.
    auto_setup: bool = False

    # --- Speech-to-text proxy (connect.md section 8) ---------------------
    stt_model: str = "whisper-large-v3"

    # --- RAG (connect.md section 5) --------------------------------------
    # Gemini embeddings by default (free tier, multilingual). The vector size
    # MUST match the loan_chunks/scheme_chunks column (vector(768)); changing
    # the model later means re-embedding every chunk.
    embedding_api_key: str | None = None
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    # Folder (relative to backend/) that `python -m rag.folder_sync` reads PDFs from.
    rag_documents_dir: str = "documents"
    rag_top_k: int = 5
    rag_min_similarity: float = 0.45
    rag_classify_min_confidence: float = 0.7
    rag_chunk_chars: int = 2400  # ~600 tokens
    rag_chunk_overlap_chars: int = 400  # ~100 tokens


settings = Settings()
