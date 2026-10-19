from fastapi import APIRouter

from app.dependencies import Session
from app.responses import download_response
from app.services import documents as service

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/download")
def download_created_file(current: Session, file_id: str | None = None):
    return download_response(*service.generated(current[1], file_id))
