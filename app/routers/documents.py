from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.dependencies import Session
from app.responses import download_response
from app.schemas.documents import RemovalResponse, UploadResponse
from app.services import documents as service

router = APIRouter(prefix="/document", tags=["document"])


@router.post("", response_model=UploadResponse)
async def upload_document(current: Session, file: UploadFile = File(...)):
    try:
        data = await file.read()
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
