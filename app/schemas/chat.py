from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.documents import DownloadInfo, UploadResponse
from app.schemas.conversations import ConversationResponse


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class Source(BaseModel):
    title: str
    url: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    display_answer: str
    sources: list[Source]
    uploads: list[UploadResponse]
    generated_files: list[DownloadInfo]


class StateResponse(BaseModel):
    user_id: int | None
    conversation_id: int | None
    conversations: list[ConversationResponse]
    messages: list[Message]
    uploads: list[UploadResponse]
    generated_files: list[DownloadInfo]
