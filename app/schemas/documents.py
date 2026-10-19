from pydantic import BaseModel, Field


class DownloadInfo(BaseModel):
    id: str
    filename: str


class UploadResponse(DownloadInfo):
    status: str
    edits: list[DownloadInfo] = Field(default_factory=list)


class RemovalResponse(BaseModel):
    ok: bool
