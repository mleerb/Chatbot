from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.conversations import ConversationResponse
from app.schemas.documents import DownloadInfo, UploadResponse


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    replace_from: int | None = Field(default=None, ge=0)


class RatingRequest(BaseModel):
    index: int = Field(ge=0)
    rating: Literal["up", "down"] | None = None


class RatingResponse(BaseModel):
    rating: Literal["up", "down"] | None


class StopResponse(BaseModel):
    stopped: bool


class WebSource(BaseModel):
    title: str
    url: str
    kind: Literal["web"] = "web"
    marker: str = ""


class DocumentSource(BaseModel):
    kind: Literal["document"]
    id: str
    marker: str
    title: str
    file_id: str
    revision_id: str
    revision: str
    version: str
    location: str


class SourceText(DocumentSource):
    text: str


Source = WebSource | DocumentSource


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = Field(default_factory=list)
    attachments: list[DownloadInfo] = Field(default_factory=list)
    stopped: bool = False
    rating: Literal["up", "down"] | None = None


class ChatResponse(BaseModel):
    answer: str
    display_answer: str
    stopped: bool = False
    sources: list[Source]
    attachments: list[DownloadInfo] = Field(default_factory=list)
    uploads: list[UploadResponse]
    generated_files: list[DownloadInfo]
    guest_limited: bool = False
    limit_resets_at: datetime | None = None


class StateResponse(BaseModel):
    user_id: int | None
    conversation_id: int | None
    conversations: list[ConversationResponse]
    messages: list[Message]
    uploads: list[UploadResponse]
    generated_files: list[DownloadInfo]
    guest_limited: bool = False
    limit_resets_at: datetime | None = None
    upload_resets_at: datetime | None = None
