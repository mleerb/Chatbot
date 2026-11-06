from pydantic import BaseModel, Field


class DownloadInfo(BaseModel):
    id: str
    filename: str


class UploadResponse(DownloadInfo):
    status: str
    sent: bool = False
    edits: list[DownloadInfo] = Field(default_factory=list)


class UploadSettings(BaseModel):
    max_file_bytes: int
    max_conversation_files: int
    max_conversation_bytes: int
    parsing_enabled: bool
    text_extensions: list[str]
    image_extensions: list[str]
    guest_inspection_enabled: bool


class RemovalResponse(BaseModel):
    ok: bool
