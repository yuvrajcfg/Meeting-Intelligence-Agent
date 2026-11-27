from datetime import datetime
from uuid import UUID

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings
from app.rag.components import CHROMA_COLLECTION_NAME, create_vector_store


def index_transcript(
    *,
    settings: Settings,
    meeting_id: int,
    task_id: UUID,
    title: str,
    transcript: str,
    meeting_date: datetime | None,
    file_name: str | None = None,
    file_type: str | None = None,
    file_size: int | None = None,
    uploaded_at: datetime | None = None,
    indexed_at: datetime | None = None,
    original_file_path: str | None = None,
    cleaned_text_path: str | None = None,
) -> int:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=500,
        chunk_overlap=75,
    )
    chunks = splitter.split_text(transcript)
    if not chunks:
        return 0

    date_value = meeting_date.isoformat() if meeting_date is not None else ""
    documents = [
        Document(
            page_content=chunk,
            metadata={
                "meeting_id": meeting_id,
                "meeting_title": title,
                "meeting_date": date_value,
                "chunk_index": index,
                "indexing_task_id": str(task_id),
                "file_name": file_name or "",
                "file_type": file_type or "",
                "file_size": file_size if file_size is not None else 0,
                "uploaded_at": uploaded_at.isoformat() if uploaded_at else "",
                "status": "ready",
                "indexed_at": indexed_at.isoformat() if indexed_at else "",
                "chunk_count": len(chunks),
                "error_message": "",
                "original_file_path": original_file_path or "",
                "cleaned_text_path": cleaned_text_path or "",
                "chroma_collection": CHROMA_COLLECTION_NAME,
            },
        )
        for index, chunk in enumerate(chunks)
    ]
    vector_store = create_vector_store(settings)
    vector_store.delete(where={"meeting_id": meeting_id})
    vector_store.add_documents(
        documents,
        ids=[f"meeting-{meeting_id}-chunk-{index}" for index in range(len(documents))],
    )
    return len(documents)
