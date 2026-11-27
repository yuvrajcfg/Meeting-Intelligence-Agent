from fastapi import APIRouter

from app.api.routes.ask import router as ask_router
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.meetings import router as meetings_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(ask_router, tags=["questions"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(meetings_router, tags=["meetings"])
