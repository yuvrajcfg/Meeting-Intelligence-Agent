import logging
from datetime import datetime, timezone
from uuid import UUID

from redis import Redis

from app.config import get_settings
from app.rag.components import CHROMA_COLLECTION_NAME, create_chroma_client
from app.rag.indexing import index_transcript
from app.repositories.sqlserver_meeting_repository import SqlServerMeetingRepository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _create_status_repository() -> SqlServerMeetingRepository | None:
    settings = get_settings()
    if settings.database_backend == "memory":
        return None
    if not settings.sqlserver_connection_string:
        raise RuntimeError(
            "SQLSERVER_CONNECTION_STRING is required for the SQL Server backend."
        )
    return SqlServerMeetingRepository(settings.sqlserver_connection_string)


@celery_app.task(name="app.workers.tasks.index_meeting")
def index_meeting(
    meeting_id: int,
    title: str,
    transcript: str,
    meeting_date: str | None,
    task_id: str,
) -> dict[str, int | str]:
    settings = get_settings()
    indexing_task_id = UUID(task_id)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    repository: SqlServerMeetingRepository | None = None

    try:
        repository = _create_status_repository()
        meeting = repository.get(meeting_id) if repository is not None else None
        if repository is not None:
            repository.set_indexing_status(
                meeting_id,
                indexing_task_id,
                "processing",
            )

        with redis_client.lock(
            f"meeting-index-lock:{meeting_id}",
            timeout=3600,
            blocking_timeout=3600,
        ):
            current_task_id = redis_client.get(f"meeting-index-current:{meeting_id}")
            if current_task_id != task_id:
                return {"status": "superseded", "chunks": 0}

            parsed_meeting_date = (
                datetime.fromisoformat(meeting_date) if meeting_date else None
            )
            indexed_at = datetime.now(timezone.utc)
            chunk_count = index_transcript(
                settings=settings,
                meeting_id=meeting_id,
                task_id=indexing_task_id,
                title=title,
                transcript=transcript,
                meeting_date=parsed_meeting_date,
                file_name=meeting.file_name if meeting else None,
                file_type=meeting.file_type if meeting else None,
                file_size=meeting.file_size if meeting else None,
                uploaded_at=meeting.uploaded_at if meeting else None,
                indexed_at=indexed_at,
                original_file_path=(
                    meeting.original_file_path if meeting else None
                ),
                cleaned_text_path=meeting.cleaned_text_path if meeting else None,
            )

        if repository is not None:
            repository.set_indexing_status(
                meeting_id,
                indexing_task_id,
                "ready",
                indexed_at=indexed_at,
                chunk_count=chunk_count,
            )
        return {"status": "ready", "chunks": chunk_count}
    except Exception as error:
        message = f"Indexing failed ({type(error).__name__}). Check worker logs."
        logger.error("Indexing failed for meeting %s (%s)", meeting_id, type(error).__name__)
        if repository is not None:
            try:
                repository.set_indexing_status(
                    meeting_id,
                    indexing_task_id,
                    "failed",
                    message,
                )
            except Exception as status_error:
                logger.error(
                    "Could not save indexing failure status for meeting %s (%s)",
                    meeting_id,
                    type(status_error).__name__,
                )
        raise
    finally:
        redis_client.close()
        if repository is not None:
            repository.close()


@celery_app.task(name="app.workers.tasks.delete_meeting_vectors")
def delete_meeting_vectors(meeting_id: int, task_id: str) -> dict[str, str]:
    settings = get_settings()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        with redis_client.lock(
            f"meeting-index-lock:{meeting_id}",
            timeout=3600,
            blocking_timeout=3600,
        ):
            current_task_id = redis_client.get(f"meeting-index-current:{meeting_id}")
            if current_task_id != task_id:
                return {"status": "superseded"}

            collection = create_chroma_client(settings).get_or_create_collection(
                name=CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            collection.delete(where={"meeting_id": meeting_id})
        return {"status": "deleted"}
    finally:
        redis_client.close()
