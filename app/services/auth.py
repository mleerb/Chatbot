import secrets
import threading
import time
from collections import OrderedDict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.exc import IntegrityError

from app.core.errors import ServiceError
from app.db import repository
from app.services.sessions import COOKIE, SESSION_TTL, ChatSession, sessions, sessions_lock

hasher = PasswordHasher()
dummy_hash = hasher.hash(secrets.token_urlsafe(24))
attempts = OrderedDict()
attempts_lock = threading.Lock()


def throttle(address):
    now = time.monotonic()
    with attempts_lock:
        recent = [stamp for stamp in attempts.pop(address, []) if now - stamp < 300]
        if len(recent) >= 10:
            attempts[address] = recent
            raise ServiceError(429, "Too many attempts. Try again in five minutes.")
        attempts[address] = recent + [now]
        while len(attempts) > 1000:
            attempts.popitem(last=False)


def register(email, name, password):
    name = name.strip()
    if not name:
        raise ServiceError(422, "Enter your name")
    try:
        return repository.create_account(email.lower(), name, hasher.hash(password))
    except IntegrityError as exc:
        raise ServiceError(409, "Unable to create this account. Try logging in or use another email.") from exc


def login(email, password):
    account = repository.account_by_email(email.lower())
    try:
        valid = hasher.verify(account["password_hash"] if account else dummy_hash, password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or account is None:
        raise ServiceError(401, "Email or password is incorrect")
    return {key: account[key] for key in ("id", "name", "email")}


def establish(current, account, response, secure=False):
    from app.services.users import select_user

    replacement = ChatSession(account=account)
    select_user(replacement, account["id"])
    replace_session(current, replacement, response, secure, persistent=True)


def guest(current, response, secure=False):
    if current[1].account is not None:
        raise ServiceError(409, "Log out before starting a guest session")
    if current[1].guest:
        return current[0]
    return replace_session(current, ChatSession(guest=True), response, secure)


def replace_session(current, replacement, response, secure=False, persistent=False):
    token, previous = current
    with previous.lock:
        with sessions_lock:
            if sessions.get(token) is not previous:
                raise ServiceError(401, "Session expired. Try again.")
            del sessions[token]
            token = secrets.token_urlsafe(32)
            sessions[token] = replacement
        previous.clear()
    if not replacement.guest:
        if "set-cookie" in response.headers:
            del response.headers["set-cookie"]
        response.set_cookie(COOKIE, token, max_age=SESSION_TTL if persistent else None,
                            httponly=True, samesite="strict", secure=secure)
    return token


def logout(current, response):
    token, previous = current
    was_guest = previous.guest
    with previous.lock:
        with sessions_lock:
            sessions.pop(token, None)
        previous.clear()
    if not was_guest:
        if "set-cookie" in response.headers:
            del response.headers["set-cookie"]
        response.delete_cookie(COOKIE, httponly=True, samesite="strict")


def close_guest(current):
    from app.services.sessions import GUEST_CLOSE_DELAY

    token, previous = current
    if not previous.guest:
        raise ServiceError(403, "Guest sessions only")

    def discard():
        with previous.lock:
            with sessions_lock:
                if sessions.get(token) is not previous or previous.close_timer is not timer:
                    return
                sessions.pop(token, None)
                previous.close_timer = None
            previous.clear()

    timer = threading.Timer(GUEST_CLOSE_DELAY, discard)
    timer.daemon = True
    with sessions_lock:
        if sessions.get(token) is previous:
            previous.close_timer = timer
            timer.start()
