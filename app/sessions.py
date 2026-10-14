import secrets
import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, Response

COOKIE = "chat_session"
SESSION_TTL = 60 * 60 * 12
MAX_SESSIONS = 100


@dataclass
class ChatSession:
    user_id: int | None = None
    history: list[dict] = field(default_factory=list)
    document: str = ""
    image_url: str = ""
    filename: str = ""
    file_bytes: bytes | None = None
    file_status: str = ""
    generated_filename: str = ""
    generated_bytes: bytes | None = None
    edited_bytes: bytes | None = None
    touched: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_upload(self, filename: str, data: bytes, text: str, image_url: str, status: str) -> None:
        self.document = text
        self.image_url = image_url
        self.filename = filename
        self.file_bytes = data
        self.edited_bytes = None
        self.file_status = status

    def clear_upload(self) -> None:
        self.document = ""
        self.image_url = ""
        self.filename = ""
        self.file_bytes = None
        self.edited_bytes = None
        self.file_status = ""


sessions: dict[str, ChatSession] = {}
sessions_lock = threading.Lock()


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
