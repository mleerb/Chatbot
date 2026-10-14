from fastapi import APIRouter, HTTPException, Request, Response

from app.sessions import session_for
from app.download import download_response

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/download")
def download_created_file(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        if session.generated_bytes is None:
            raise HTTPException(status_code=404, detail="No generated file available")
        return download_response(session.generated_filename, session.generated_bytes)
