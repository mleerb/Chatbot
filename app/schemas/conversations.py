from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    pinned: bool


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    pinned: bool | None = None


class DeleteResponse(BaseModel):
    ok: bool
