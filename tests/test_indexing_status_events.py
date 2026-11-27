import json
from types import SimpleNamespace
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository
from app.api.routes.meetings import router as meetings_router
from app.config import Settings
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.schemas.meeting import MeetingCreate


class IndexingStatusEventTests(unittest.TestCase):
    def test_sse_stream_emits_status_changes_until_indexing_finishes(self) -> None:
        repository = InMemoryMeetingRepository()
        task_id = uuid4()
        meeting = repository.create(
            MeetingCreate(title="Planning", transcript="Discuss launch."),
            task_id,
        )
        repository.set_indexing_status(meeting.id, task_id, "processing")
        application = FastAPI()
        application.include_router(meetings_router, prefix="/api/v1")
        application.dependency_overrides[get_meeting_repository] = lambda: repository
        settings = Settings(_env_file=None, indexing_mode="local")

        async def finish_indexing(_: float) -> None:
            repository.set_indexing_status(meeting.id, task_id, "ready")

        with (
            patch("app.api.routes.meetings.get_settings", return_value=settings),
            patch(
                "app.api.routes.meetings.asyncio",
                SimpleNamespace(sleep=finish_indexing),
            ),
        ):
            response = TestClient(application).get(
                f"/api/v1/meetings/{meeting.id}/index-status/events"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        messages = [
            json.loads(line[len("data: "):])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual([message["status"] for message in messages], ["processing", "ready"])


if __name__ == "__main__":
    unittest.main()
