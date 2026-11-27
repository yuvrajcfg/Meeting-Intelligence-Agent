import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

from app.config import Settings
from app.rag.indexing import index_transcript


class TranscriptChunkMetadataTests(unittest.TestCase):
    def test_indexed_chunks_include_upload_and_indexing_metadata(self) -> None:
        uploaded_at = datetime(2026, 11, 27, 8, 0, tzinfo=timezone.utc)
        indexed_at = datetime(2026, 11, 27, 8, 1, tzinfo=timezone.utc)
        splitter = Mock()
        splitter.split_text.return_value = ["First chunk.", "Second chunk."]
        vector_store = Mock()

        with (
            patch(
                "app.rag.indexing.RecursiveCharacterTextSplitter.from_tiktoken_encoder",
                return_value=splitter,
            ),
            patch("app.rag.indexing.create_vector_store", return_value=vector_store),
        ):
            chunk_count = index_transcript(
                settings=Settings(_env_file=None),
                meeting_id=17,
                task_id=uuid4(),
                title="Planning",
                transcript="First chunk. Second chunk.",
                meeting_date=None,
                file_name="planning.txt",
                file_type=".txt",
                file_size=512,
                uploaded_at=uploaded_at,
                indexed_at=indexed_at,
                original_file_path="storage/transcripts/meeting_17/planning.txt",
                cleaned_text_path=(
                    "storage/transcripts/meeting_17/planning.txt.cleaned.txt"
                ),
            )

        documents = vector_store.add_documents.call_args.args[0]
        self.assertEqual(chunk_count, 2)
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].metadata["meeting_id"], 17)
        self.assertEqual(documents[0].metadata["file_name"], "planning.txt")
        self.assertEqual(documents[0].metadata["file_type"], ".txt")
        self.assertEqual(documents[0].metadata["file_size"], 512)
        self.assertEqual(documents[0].metadata["uploaded_at"], uploaded_at.isoformat())
        self.assertEqual(documents[0].metadata["indexed_at"], indexed_at.isoformat())
        self.assertEqual(documents[0].metadata["status"], "ready")
        self.assertEqual(documents[0].metadata["chunk_count"], 2)
        self.assertEqual(documents[0].metadata["error_message"], "")
        self.assertEqual(
            documents[0].metadata["original_file_path"],
            "storage/transcripts/meeting_17/planning.txt",
        )
        self.assertEqual(
            documents[0].metadata["cleaned_text_path"],
            "storage/transcripts/meeting_17/planning.txt.cleaned.txt",
        )
        self.assertEqual(
            documents[0].metadata["chroma_collection"],
            "meeting_transcripts",
        )


if __name__ == "__main__":
    unittest.main()
