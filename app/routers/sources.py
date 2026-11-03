from fastapi import APIRouter, Response

from app.dependencies import Session
from app.schemas.chat import SourceText
from app.services.citations import source_text

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceText)
def view_source(source_id: str, current: Session, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return source_text(current[1], source_id)
