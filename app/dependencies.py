import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response

from app.services.sessions import COOKIE, MAX_SESSIONS, SESSION_TTL, ChatSession, sessions, sessions_lock


def session_for(request: Request, response: Response) -> tuple[str, ChatSession]:
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(status_code=403, detail="Cross-site requests are not allowed")
        origin = request.headers.get("origin")
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        if origin and urlsplit(origin).netloc != host:
            raise HTTPException(status_code=403, detail="Cross-site requests are not allowed")
    guest_token = request.headers.get("x-guest-session")
    if guest_token:
        with sessions_lock:
            session = sessions.get(guest_token)
            if session is None or not session.guest:
                raise HTTPException(status_code=401, detail="Guest tab has ended. Start a new chat.")
            if session.close_timer is not None:
                session.close_timer.cancel()
                session.close_timer = None
            session.touched = time.monotonic()
        return guest_token, session
    token = request.cookies.get(COOKIE)
    now = time.monotonic()
    with sessions_lock:
        for key, value in list(sessions.items()):
            if not value.guest and now - value.touched > SESSION_TTL:
                del sessions[key]
        if token not in sessions:
            if len(sessions) >= MAX_SESSIONS:
                raise HTTPException(status_code=503, detail="Too many active sessions; try again later")
            token = secrets.token_urlsafe(32)
            sessions[token] = ChatSession()
            response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=False)
        session = sessions[token]
        session.touched = now
    return token, session


def authenticated(current: Annotated[tuple[str, ChatSession], Depends(session_for)]):
    if current[1].account is None:
        raise HTTPException(status_code=401, detail="Log in to continue")
    return current


def workspace(current: Annotated[tuple[str, ChatSession], Depends(session_for)]):
    if current[1].account is None and not current[1].guest:
        raise HTTPException(status_code=401, detail="Log in or continue as guest")
    return current


AccountSession = Annotated[tuple[str, ChatSession], Depends(authenticated)]
Session = Annotated[tuple[str, ChatSession], Depends(workspace)]
BrowserSession = Annotated[tuple[str, ChatSession], Depends(session_for)]
