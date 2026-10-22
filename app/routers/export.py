from fastapi import APIRouter

from app.dependencies import Session
from app.responses import download_response
from app.schemas.export import ExportRequest
from app.services import export as service

router = APIRouter(prefix="/export", tags=["export"])


@router.post("")
def export_answer(payload: ExportRequest, current: Session):
    return download_response(*service.export(payload.content, payload.format))
