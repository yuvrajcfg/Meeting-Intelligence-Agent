import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_meeting_repository
from app.api.routes.meetings import router as meetings_router
from app.config import Settings
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.services.transcripts import store_original_transcript


class TranscriptStorageTests(unittest.TestCase):
    def test_upload_api_keeps_original_file_and_returns_pending_status(self) -> None:
        repository = InMemoryMeetingRepository()
        application = FastAPI()
        application.include_router(meetings_router, prefix="/api/v1")
        application.dependency_overrides[get_meeting_repository] = lambda: repository

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = Settings(
                _env_file=None,
                transcript_storage_directory=Path(temporary_directory) / "transcripts",
            )
            original = b"Original meeting transcript.\r\n"
            with (
                patch("app.api.routes.meetings.get_settings", return_value=settings),
                patch(
                    "app.api.routes.meetings.start_meeting_index",
                    side_effect=lambda *args: repository.get(args[1].id),
                ),
            ):
                response = TestClient(application).post(
                    "/api/v1/meetings/upload",
                    files={"file": ("Team-Meeting.Final.TXT", original, "text/plain")},
                )

            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["indexing_status"], "pending")
            self.assertEqual(response.json()["status"], "pending")
            self.assertEqual(response.json()["file_name"], "Team-Meeting.Final.TXT")
            self.assertEqual(response.json()["file_type"], ".txt")
            self.assertEqual(response.json()["file_size"], len(original))
            self.assertEqual(response.json()["chroma_collection"], "meeting_transcripts")
            stored_file = (
                Path(temporary_directory)
                / "transcripts"
                / "meeting_1"
                / "Team-Meeting.Final.TXT"
            )
            self.assertEqual(stored_file.read_bytes(), original)
            cleaned_file = stored_file.with_name(
                f"{stored_file.name}.cleaned.txt"
            )
            self.assertEqual(
                cleaned_file.read_text(encoding="utf-8"),
                "Original meeting transcript.",
            )
            self.assertEqual(response.json()["original_file_path"], str(stored_file))
            self.assertEqual(response.json()["cleaned_text_path"], str(cleaned_file))

    def test_original_upload_bytes_are_saved_with_meeting_id_and_extension(self) -> None:
        content = b"\xef\xbb\xbfOriginal transcript bytes.\r\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = store_original_transcript(
                meeting_id=101,
                filename="meeting source.TXT",
                content=content,
                storage_directory=Path(temporary_directory),
            )

            self.assertEqual(path.name, "meeting source.TXT")
            self.assertEqual(path.parent.name, "meeting_101")
            self.assertEqual(path.read_bytes(), content)

    def test_unsupported_original_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(ValueError):
                store_original_transcript(
                    meeting_id=102,
                    filename="transcript.exe",
                    content=b"not a transcript",
                    storage_directory=Path(temporary_directory),
                )


if __name__ == "__main__":
    unittest.main()
