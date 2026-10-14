from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from app.sessions import session_for
from app.download import download_response
from app.extract import file_context

router = APIRouter(prefix="/api/document", tags=["document"])


@router.post("")
async def upload_document(request: Request, response: Response, file: UploadFile = File(...)):
    _, session = session_for(request, response)
    filename = Path((file.filename or "").replace("\\", "/")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Choose a file")
    try:
        data = await file.read()
    finally:
        await file.close()
    text, image_url, status = await run_in_threadpool(file_context, filename, data)
    with session.lock:
        if session.user_id is None:
            raise HTTPException(status_code=400, detail="Select a user before uploading")
        session.set_upload(filename, data, text, image_url, status)
    return {"filename": filename, "status": status}


@router.get("/download")
def download_document(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        if session.file_bytes is None:
            raise HTTPException(status_code=404, detail="No file uploaded")
        return download_response(session.filename, session.file_bytes)


@router.get("/edited")
def download_edited_document(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        if session.edited_bytes is None:
            raise HTTPException(status_code=404, detail="No edited file available")
        return download_response(session.filename, session.edited_bytes)


@router.delete("")
def remove_document(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        session.clear_upload()
    return {"ok": True}
