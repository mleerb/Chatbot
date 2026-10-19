import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response

from app.services.sessions import COOKIE, MAX_SESSIONS, SESSION_TTL, ChatSession, sessions, sessions_lock


def session_for(request: Request, response: Response) -> tuple[str, ChatSession]:
    token = request.cookies.get(COOKIE)
    now = time.monotonic()
    with sessions_lock:
        for key, value in list(sessions.items()):
            if now - value.touched > SESSION_TTL:
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


Session = Annotated[tuple[str, ChatSession], Depends(session_for)]
