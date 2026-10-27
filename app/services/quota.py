import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.errors import ServiceError
from app.db import repository

USER_TOKEN_LIMIT = int(os.getenv("USER_TOKEN_LIMIT", "500000"))
UPLOAD_LIMIT = int(os.getenv("UPLOAD_LIMIT", "5"))
IMAGE_LIMIT = int(os.getenv("IMAGE_LIMIT", "10"))
LIMIT_TIMEZONE = ZoneInfo(os.getenv("LIMIT_TIMEZONE", "").strip() or "Asia/Ho_Chi_Minh")
LIMIT_MESSAGE = "Daily limit reached. Chat and uploads open again after midnight."
UPLOAD_LIMIT_MESSAGE = f"Daily upload limit reached ({UPLOAD_LIMIT} files a day). You can upload more files after midnight."
IMAGE_LIMIT_MESSAGE = "Daily image limit reached; no image was created. Tell the user they can create more images after midnight."


def now():
    return datetime.now(timezone.utc)


def today():
    return now().astimezone(LIMIT_TIMEZONE).date()


def midnight(day):
    return datetime.combine(day, time(), LIMIT_TIMEZONE).astimezone(timezone.utc)


def next_midnight():
    return midnight(today() + timedelta(days=1))


def current(user_id):
    item = repository.usage(user_id) if user_id is not None else None
    if item is None:
        return None
    start = item["window_start"]
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    return item if start >= midnight(today()) else None


def resets_at(user_id):
    item = current(user_id)
    return next_midnight() if item is not None and item["tokens"] >= USER_TOKEN_LIMIT else None


def upload_resets_at(user_id):
    item = current(user_id)
    return next_midnight() if item is not None and item["uploads"] >= UPLOAD_LIMIT else None


def check_limit(user_id):
    if resets_at(user_id) is not None:
        raise ServiceError(403, LIMIT_MESSAGE)


def check_upload(user_id):
    check_limit(user_id)
    if upload_resets_at(user_id) is not None:
        raise ServiceError(403, UPLOAD_LIMIT_MESSAGE)


def take_upload(user_id):
    if not repository.add_count(user_id, "uploads", midnight(today()), UPLOAD_LIMIT):
        raise ServiceError(403, UPLOAD_LIMIT_MESSAGE)


def take_image(user_id):
    return repository.add_count(user_id, "images", midnight(today()), IMAGE_LIMIT)


def release_image(user_id):
    repository.remove_count(user_id, "images", midnight(today()))


def record(user_id, tokens):
    repository.add_usage(user_id, tokens, midnight(today()))
