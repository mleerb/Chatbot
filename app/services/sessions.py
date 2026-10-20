import threading
import time
from dataclasses import dataclass, field
from uuid import uuid4

COOKIE = "chat_session"
SESSION_TTL = 60 * 60 * 12
GUEST_CLOSE_DELAY = 15
MAX_SESSIONS = 100


def file_id() -> str:
    return uuid4().hex


@dataclass
class Download:
    filename: str
    data: bytes
    id: str = field(default_factory=file_id)

    def summary(self) -> dict:
        return {"id": self.id, "filename": self.filename}


@dataclass
class Upload:
    filename: str
    data: bytes
    document: str
    image_url: str
    status: str
    id: str = field(default_factory=file_id)
    edits: list[Download] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "edits": [edit.summary() for edit in self.edits],
        }


@dataclass
class ChatSession:
    user_id: int | None = None
    account: dict | None = None
    guest: bool = False
    close_timer: threading.Timer | None = field(default=None, repr=False)
    guest_messages: list[dict] = field(default_factory=list)
    guest_conversation: dict | None = None
    conversation_id: int | None = None
    history: list[dict] = field(default_factory=list)
    uploads: dict[str, Upload] = field(default_factory=dict)
    generated: dict[str, Download] = field(default_factory=dict)
    touched: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def latest_upload(self) -> Upload | None:
        return next(reversed(self.uploads.values()), None)

    @property
    def latest_generated(self) -> Download | None:
        return next(reversed(self.generated.values()), None)

    def file_state(self) -> dict:
        return {
            "uploads": [item.summary() for item in self.uploads.values()],
            "generated_files": [item.summary() for item in self.generated.values()],
        }

    def clear_upload(self) -> None:
        self.uploads.clear()

    def clear(self) -> None:
        if self.close_timer is not None:
            self.close_timer.cancel()
            self.close_timer = None
        self.user_id = None
        self.account = None
        self.guest = False
        self.conversation_id = None
        self.guest_conversation = None
        self.history.clear()
        self.guest_messages.clear()
        self.uploads.clear()
        self.generated.clear()


sessions: dict[str, ChatSession] = {}
sessions_lock = threading.Lock()
