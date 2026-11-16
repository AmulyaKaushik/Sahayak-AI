"""Round-robin over several Groq API keys.

Groq's free tier limits tokens per minute per key, so spreading calls over
more keys raises the ceiling. Set GROQ_API_KEY and/or GROQ_API_KEYS (comma
separated); every call to next_groq_key() returns the next one in turn."""

import re
import threading

from settings import settings

_lock = threading.Lock()
_counter = 0


def groq_keys() -> list[str]:
    raw = f"{settings.groq_api_key or ''},{settings.groq_api_keys or ''}"
    keys: list[str] = []
    for key in re.split(r"[,\s]+", raw):
        if key and key not in keys:
            keys.append(key)
    return keys


def next_groq_key() -> str | None:
    global _counter
    keys = groq_keys()
    if not keys:
        return None
    with _lock:
        key = keys[_counter % len(keys)]
        _counter += 1
    return key
