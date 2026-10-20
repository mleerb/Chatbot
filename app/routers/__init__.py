from fastapi import APIRouter

from app.routers import chat, conversations, documents, generated, users

router = APIRouter(prefix="/api")
router.include_router(chat.router)
router.include_router(documents.router)
router.include_router(users.router)
router.include_router(conversations.router)
router.include_router(generated.router)
