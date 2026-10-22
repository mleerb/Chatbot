from typing import Literal

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    format: Literal["md", "docx", "pdf"]
