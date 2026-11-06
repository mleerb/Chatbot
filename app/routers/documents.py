from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core import limits
from app.core.file_types import IMAGE_EXTENSIONS, TEXT_EXTENSIONS
from app.dependencies import Session
from app.responses import download_response
from app.schemas.documents import RemovalResponse, UploadResponse, UploadSettings
from app.services import documents as service
from app.services import parse, workspace

router = APIRouter(prefix="/document", tags=["document"])


@router.get("/settings", response_model=UploadSettings)
def upload_settings(current: Session):
    maximum, count, budget = limits.upload_limits()
    return {"max_file_bytes": maximum, "max_conversation_files": count,
            "max_conversation_bytes": budget, "parsing_enabled": parse.enabled(),
            "text_extensions": sorted(TEXT_EXTENSIONS), "image_extensions": sorted(IMAGE_EXTENSIONS),
            "guest_inspection_enabled": current[1].guest and workspace.enabled(current[1])}


@router.post("", response_model=UploadResponse)
async def upload_document(current: Session, file: UploadFile = File(...)):
    try:
        maximum = limits.upload_limits()[0]
        if file.size is not None:
            limits.check_upload(file.size)
        data = await file.read(maximum + 1)
        limits.check_upload(len(data))
    finally:
        await file.close()
    return await run_in_threadpool(service.upload, current[1], file.filename or "", data)


@router.get("/download")
def download_document(current: Session, file_id: str | None = None):
    return download_response(*service.original(current[1], file_id))


@router.get("/edited")
def download_edited_document(current: Session, file_id: str | None = None,
                             revision_id: str | None = None):
    return download_response(*service.edited(current[1], file_id, revision_id))


@router.delete("", response_model=RemovalResponse)
def remove_document(current: Session, file_id: str | None = None):
    return service.remove(current[1], file_id)
