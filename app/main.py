from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.exceptions import MeetingNotFoundError
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.repositories.protocols import MeetingRepository
from app.repositories.sqlserver_meeting_repository import SqlServerMeetingRepository


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.database_backend == "sqlserver":
        if not settings.sqlserver_connection_string:
            raise ValueError(
                "SQLSERVER_CONNECTION_STRING is required when DATABASE_BACKEND=sqlserver."
            )
        repository: MeetingRepository = SqlServerMeetingRepository(
            settings.sqlserver_connection_string
        )
    else:
        repository = InMemoryMeetingRepository()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            if isinstance(repository, SqlServerMeetingRepository):
                repository.check_connection()
            yield
        finally:
            if isinstance(repository, SqlServerMeetingRepository):
                repository.close()

    application = FastAPI(
        title=settings.app_name,
        description="Ask questions about meeting transcripts.",
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.state.meeting_repository = repository
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    chat_html = (
        Path(__file__)
        .parent.joinpath("static", "index.html")
        .read_text(encoding="utf-8")
        .replace("__API_V1_PREFIX__", settings.api_v1_prefix)
    )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def home() -> HTMLResponse:
        return HTMLResponse(
            content=(
                "<!doctype html>"
                '<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                "<title>Meeting Intelligence Agent</title></head>"
                "<body><main>"
                "<h1>Meeting Intelligence Agent</h1>"
                "<p>The API is running. Use the interactive documentation "
                "to explore the available endpoints.</p>"
                '<p><a href="/chat">Open the meeting chat</a></p>'
                '<p><a href="/docs">Open API documentation</a></p>'
                f'<p><a href="{settings.api_v1_prefix}/health">Check API health</a></p>'
                "</main></body></html>"
            )
        )

    @application.get("/chat", response_class=HTMLResponse, include_in_schema=False)
    async def chat_page() -> HTMLResponse:
        return HTMLResponse(content=chat_html)

    @application.exception_handler(MeetingNotFoundError)
    async def meeting_not_found_handler(
        request: Request,
        exc: MeetingNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    return application


app = create_app()
