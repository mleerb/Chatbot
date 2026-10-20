from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import config
from app.core.errors import ServiceError
from app.core.trace import flush_traces
from app.db import repository
from app.db.connection import dispose_engine
from app.routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        repository.initialize()
        yield
    finally:
        try:
            flush_traces()
        finally:
            dispose_engine()


def create_app() -> FastAPI:
    application = FastAPI(title="Aster", lifespan=lifespan)
    application.include_router(router)

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    return application


app = create_app()
