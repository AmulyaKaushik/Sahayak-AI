"""POST /api/v1/transcribe: forwards audio to Groq Whisper with the
server-side key, so the app no longer ships any secret."""

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from security.auth import get_current_customer_id
from settings import settings
from workers.keys import next_groq_key

router = APIRouter(prefix="/api/v1", tags=["speech"])

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Groq's own upload limit
TIMEOUT_SECONDS = 60.0

# Whisper reports a language name ("hindi") or ISO code ("hi"); the app wants BCP-47.
_LANGUAGE_TO_BCP47 = {
    "hindi": "hi-IN", "hi": "hi-IN", "english": "en-IN", "en": "en-IN",
    "bengali": "bn-IN", "bn": "bn-IN", "marathi": "mr-IN", "mr": "mr-IN",
    "tamil": "ta-IN", "ta": "ta-IN", "telugu": "te-IN", "te": "te-IN",
    "gujarati": "gu-IN", "gu": "gu-IN", "kannada": "kn-IN", "kn": "kn-IN",
    "malayalam": "ml-IN", "ml": "ml-IN", "punjabi": "pa-IN", "pa": "pa-IN",
    "urdu": "ur-IN", "ur": "ur-IN",
}
# Whisper invents text ("Thank you.") for silence; drop segments it flags itself.
_NO_SPEECH_PROB = 0.6
_AVG_LOGPROB = -1.0


class TranscribeResponse(BaseModel):
    text: str
    language: str


def _is_silence(segment: dict) -> bool:
    return (
        segment.get("no_speech_prob", 0) > _NO_SPEECH_PROB
        and segment.get("avg_logprob", 0) < _AVG_LOGPROB
    )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    customer_id: str = Depends(get_current_customer_id),
) -> TranscribeResponse:
    api_key = next_groq_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Speech-to-text is not configured")

    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=422, detail="Empty audio file")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio is larger than 25 MB")

    data = {"model": settings.stt_model, "response_format": "verbose_json"}
    if language:  # optional hint, e.g. "hi"
        data["language"] = language.split("-")[0].lower()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (file.filename or "speech.m4a", audio, file.content_type or "audio/m4a")},
                data=data,
            )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Speech-to-text service failed")

    segments = body.get("segments")
    text = (
        "".join(s.get("text", "") for s in segments if not _is_silence(s)).strip()
        if segments
        else str(body.get("text", "")).strip()
    )
    detected = str(body.get("language", "")).lower()
    return TranscribeResponse(text=text, language=_LANGUAGE_TO_BCP47.get(detected, "en-IN"))
