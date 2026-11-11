import math
import os

from app.core.errors import ServiceError

MIB = 1024 * 1024
TIMEOUTS = {
    "CHAT_TIMEOUT_SECONDS": 180,
    "TITLE_TIMEOUT_SECONDS": 90,
    "EMBEDDING_TIMEOUT_SECONDS": 60,
    "IMAGE_TIMEOUT_SECONDS": 300,
    "SEARCH_TIMEOUT_SECONDS": 60,
    "PARSE_REQUEST_TIMEOUT_SECONDS": 90,
    "PARSE_TIMEOUT_SECONDS": 600,
    "LANGFUSE_TIMEOUT_SECONDS": 60,
    "DATABASE_CONNECT_TIMEOUT_SECONDS": 15,
}


def positive(name: str, default: int, integer: bool = False):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive {'integer' if integer else 'number'}") from None
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"{name} must be positive and finite")
    return value


def upload_limits() -> tuple[int, int, int]:
    return (positive("UPLOAD_MAX_MB", 20, True) * MIB,
            positive("CONVERSATION_MAX_FILES", 20, True),
            positive("CONVERSATION_MAX_UPLOAD_MB", 100, True) * MIB)


def timeout(name: str) -> float:
    return positive(name, TIMEOUTS[name])


def validate():
    upload_limits()
    for name, default in TIMEOUTS.items():
        positive(name, default, name in {"LANGFUSE_TIMEOUT_SECONDS", "DATABASE_CONNECT_TIMEOUT_SECONDS"})


def check_upload(size: int, count: int = 0, total: int = 0):
    maximum, files, budget = upload_limits()
    if size > maximum:
        raise ServiceError(413, f"File is too large. Maximum upload size is {maximum // MIB} MiB.")
    if count >= files:
        raise ServiceError(409, f"Conversation file limit reached ({files} uploaded files). Remove a file or start a new conversation. Existing files are unchanged.")
    if total + size > budget:
        raise ServiceError(409, f"Conversation upload storage limit reached ({budget // MIB} MiB). Remove a file or start a new conversation. Existing files are unchanged.")
