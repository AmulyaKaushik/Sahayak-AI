from pydantic import BaseModel


class WorkerNarrationResult(BaseModel):
    scheme_id: str
    eligible: bool  # copied verbatim from the engine result, never from the LLM
    satisfied: list[str]
    missing: list[str]
    completion_fraction: float
    narration: str
    extracted_fields: dict
