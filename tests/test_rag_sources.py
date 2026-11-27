import unittest
from uuid import uuid4
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableLambda

from app.api.dependencies import get_meeting_repository
from app.api.routes.ask import ask_question as ask_route
from app.api.routes.chat import router as chat_router
from app.config import Settings
from app.rag.answering import answer_question
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.repositories.protocols import MeetingRepository
from app.schemas.ask import AskRequest
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.schemas.meeting import MeetingCreate


class RagSourceResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None)
        self.repository = InMemoryMeetingRepository()
        self.task_id = uuid4()
        self.meeting = self.repository.create(
            MeetingCreate(title="Meeting Transcript 1", transcript="Private transcript."),
            self.task_id,
        )
        self.repository.set_indexing_status(
            self.meeting.id,
            self.task_id,
            "ready",
        )
        self.document = Document(
            page_content="Private transcript chunk contents.",
            metadata={
                "meeting_id": self.meeting.id,
                "meeting_title": "Meeting Transcript 1",
                "indexing_task_id": str(self.task_id),
                "chunk_index": 0,
                "speaker_name": "Yuvraj",
                "start_timestamp": "00:00:00",
                "end_timestamp": "00:00:15",
            },
        )
        self.vector_store = Mock()
        self.vector_store.similarity_search.return_value = [self.document]
        self.prompt_texts: list[str] = []
        self.model = RunnableLambda(self._answer)

    def _answer(self, prompt: PromptValue) -> str:
        self.prompt_texts.append(prompt.to_string())
        return "Yuvraj owns the task [S1]."

    def _answer_request(self, question: str):
        with (
            patch(
                "app.rag.answering.create_vector_store",
                return_value=self.vector_store,
            ),
            patch("app.rag.answering.create_chat_model", return_value=self.model),
        ):
            return answer_question(
                request=ChatRequest(question=question),
                repository=self.repository,
                settings=self.settings,
            )

    def test_normal_response_contains_metadata_but_not_chunk_text(self) -> None:
        response = self._answer_request("Who owns the task?")
        source = response.sources[0]

        self.assertEqual(source.meeting_title, "Meeting Transcript 1")
        self.assertEqual(source.chunk_index, 0)
        self.assertEqual(source.speaker_name, "Yuvraj")
        self.assertEqual(source.timestamp, "00:00:00 - 00:00:15")
        self.assertIsNone(source.excerpt)
        self.assertNotIn("Private transcript chunk contents.", str(response.model_dump()))
        self.assertIn("Private transcript chunk contents.", self.prompt_texts[0])
        self.assertIn("[S1]", response.answer)

    def test_evidence_is_included_only_when_requested(self) -> None:
        response = self._answer_request("Who owns the task? Show supporting text.")

        self.assertEqual(
            response.sources[0].excerpt,
            "Private transcript chunk contents.",
        )

    def test_missing_optional_metadata_is_left_unset(self) -> None:
        self.document.metadata.pop("speaker_name")
        self.document.metadata.pop("start_timestamp")
        self.document.metadata.pop("end_timestamp")
        self.document.metadata.pop("chunk_index")

        response = self._answer_request("Who owns the task?")

        source = response.sources[0]
        self.assertIsNone(source.chunk_index)
        self.assertIsNone(source.speaker_name)
        self.assertIsNone(source.timestamp)
        self.assertIsNone(source.excerpt)

    def test_persistent_chroma_sources_work_after_meeting_records_reset(self) -> None:
        repository_after_restart = InMemoryMeetingRepository()
        with (
            patch(
                "app.rag.answering.create_vector_store",
                return_value=self.vector_store,
            ),
            patch("app.rag.answering.create_chat_model", return_value=self.model),
        ):
            response = answer_question(
                request=ChatRequest(question="Who owns the task?"),
                repository=repository_after_restart,
                settings=self.settings,
            )

        self.assertEqual(response.sources[0].meeting_id, self.meeting.id)
        self.assertEqual(response.sources[0].meeting_title, "Meeting Transcript 1")
        self.assertIn("Private transcript chunk contents.", self.prompt_texts[-1])


class SourceApiResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(_env_file=None)
        self.repository = Mock(spec=MeetingRepository)
        self.source = ChatSource(
            source_id="S1",
            meeting_id=1,
            meeting_title="Meeting Transcript 1",
            meeting_date=None,
            chunk_index=0,
            speaker_name="Yuvraj",
            timestamp="00:00:00 - 00:00:15",
            excerpt=None,
        )

    def test_chat_api_omits_chunk_content_by_default(self) -> None:
        app = FastAPI()
        app.include_router(chat_router, prefix="/api/v1")
        app.dependency_overrides[get_meeting_repository] = lambda: self.repository
        response_body = ChatResponse(answer="Grounded answer [S1]", sources=[self.source])

        with (
            patch("app.api.routes.chat.get_settings", return_value=self.settings),
            patch("app.api.routes.chat.answer_question", return_value=response_body),
        ):
            response = TestClient(app).post(
                "/api/v1/chat",
                json={"question": "What happened?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("excerpt", response.json()["sources"][0])

    def test_ask_api_formats_compact_source_metadata(self) -> None:
        response_body = ChatResponse(answer="Grounded answer [S1]", sources=[self.source])

        with (
            patch("app.api.routes.ask.get_settings", return_value=self.settings),
            patch("app.api.routes.ask.answer_question", return_value=response_body),
        ):
            response = ask_route(
                AskRequest(question="What happened?"),
                self.repository,
            )

        self.assertEqual(
            response.sources,
            [
                "[S1] Meeting Transcript 1 | Chunk 0 | Yuvraj | "
                "00:00:00 - 00:00:15"
            ],
        )


if __name__ == "__main__":
    unittest.main()
