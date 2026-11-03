from fastapi import APIRouter, Response

from app.dependencies import Session
from app.responses import download_response, image_response
from app.services import documents as service
from app.services import preview as previews

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/download")
def download_created_file(current: Session, file_id: str | None = None):
    return download_response(*service.generated(current[1], file_id))


@router.get("/preview")
def preview_created_file(current: Session, file_id: str, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return previews.preview(current[1], file_id)


@router.get("/preview/content")
def preview_content(current: Session, file_id: str):
    data, media_type = previews.binary(current[1], file_id)
    return Response(content=data, media_type=media_type, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Content-Disposition": "attachment",
    })


@router.get("/view")
def view_created_image(current: Session, file_id: str):
    return image_response(*service.generated_image(current[1], file_id))
