import unittest
from uuid import uuid4
from unittest.mock import Mock, patch

from app.config import Settings
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.schemas.meeting import MeetingCreate
from app.services.indexing import (
    cleanup_meeting_vectors,
    get_meeting_index_status,
    start_meeting_index,
)


class LocalIndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None, indexing_mode="local")
        self.repository = InMemoryMeetingRepository()
        self.meeting = self.repository.create(
            MeetingCreate(title="Planning", transcript="Discuss launch."),
            uuid4(),
        )

    def test_local_mode_indexes_and_sets_status_without_enqueueing(self) -> None:
        with (
            patch("app.services.indexing.index_transcript", return_value=1) as index,
            patch("app.services.indexing.enqueue_meeting_index") as enqueue,
        ):
            result = start_meeting_index(
                self.repository,
                self.meeting,
                self.settings,
            )

        self.assertEqual(result.indexing_status, "indexed")
        index.assert_called_once()
        enqueue.assert_not_called()

    def test_local_index_failure_is_reported_in_meeting_status(self) -> None:
        with (
            patch(
                "app.services.indexing.index_transcript",
                side_effect=RuntimeError("provider unavailable"),
            ),
            self.assertLogs("app.services.indexing", level="ERROR"),
        ):
            result = start_meeting_index(
                self.repository,
                self.meeting,
                self.settings,
            )

        self.assertEqual(result.indexing_status, "failed")
        self.assertIn("RuntimeError", result.indexing_error or "")

    def test_celery_mode_keeps_existing_enqueue_path(self) -> None:
        settings = Settings(_env_file=None, indexing_mode="celery")
        with patch(
            "app.services.indexing.enqueue_meeting_index",
            return_value=self.meeting,
        ) as enqueue:
            result = start_meeting_index(
                self.repository,
                self.meeting,
                settings,
            )

        self.assertIs(result, self.meeting)
        enqueue.assert_called_once_with(
            self.repository,
            self.meeting,
            settings,
        )

    def test_local_vector_cleanup_is_synchronous(self) -> None:
        collection = Mock()
        client = Mock()
        client.get_or_create_collection.return_value = collection
        with patch(
            "app.services.indexing.create_chroma_client",
            return_value=client,
        ):
            task_id, error = cleanup_meeting_vectors(7, self.settings)

        self.assertIsNone(task_id)
        self.assertIsNone(error)
        collection.delete.assert_called_once_with(where={"meeting_id": 7})

    def test_local_status_does_not_query_celery(self) -> None:
        with patch("app.services.indexing.AsyncResult") as async_result:
            result = get_meeting_index_status(
                7,
                uuid4(),
                "queued",
                None,
                self.settings,
            )

        self.assertEqual(result.status, "queued")
        async_result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
