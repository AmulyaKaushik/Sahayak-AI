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
    worker_llm_model: str = "groq/openai/gpt-oss-120b"


settings = Settings()
