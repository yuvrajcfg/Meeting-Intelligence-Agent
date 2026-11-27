import logging
from uuid import UUID, uuid4

from kombu.exceptions import OperationalError
from celery.result import AsyncResult
from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings
from app.rag.components import create_chroma_client
from app.rag.indexing import index_transcript
from app.repositories.protocols import MeetingRepository
from app.schemas.meeting import IndexingStatus, MeetingIndexStatusResponse, MeetingResponse
from app.workers.celery_app import celery_app
from app.workers.tasks import delete_meeting_vectors, index_meeting

logger = logging.getLogger(__name__)


def start_meeting_index(
    repository: MeetingRepository,
    meeting: MeetingResponse,
    settings: Settings,
) -> MeetingResponse:
    if settings.indexing_mode == "celery":
        return enqueue_meeting_index(repository, meeting, settings)
    return index_meeting_locally(repository, meeting, settings)


def index_meeting_locally(
    repository: MeetingRepository,
    meeting: MeetingResponse,
    settings: Settings,
) -> MeetingResponse:
    task_id = meeting.indexing_task_id
    if task_id is None:
        raise ValueError("The meeting must have an indexing task ID before indexing.")

    repository.set_indexing_status(meeting.id, task_id, "indexing")
    try:
        index_transcript(
            settings=settings,
            meeting_id=meeting.id,
            task_id=task_id,
            title=meeting.title,
            transcript=meeting.transcript,
            meeting_date=meeting.meeting_date,
        )
    except Exception as error:
        message = f"Local indexing failed ({type(error).__name__}). Check FastAPI logs."
        logger.exception("Local indexing failed for meeting %s", meeting.id)
        repository.set_indexing_status(
            meeting.id,
            task_id,
            "failed",
            message,
        )
    else:
        repository.set_indexing_status(meeting.id, task_id, "indexed")
    return repository.get(meeting.id)


def enqueue_meeting_index(
    repository: MeetingRepository,
    meeting: MeetingResponse,
    settings: Settings,
) -> MeetingResponse:
    if meeting.indexing_task_id is None:
        raise ValueError("The meeting must have an indexing task ID before enqueueing.")

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        task_id = str(meeting.indexing_task_id)
        redis_client.set(f"meeting-index-current:{meeting.id}", task_id)
        index_meeting.apply_async(
            args=[
                meeting.id,
                meeting.title,
                meeting.transcript,
                meeting.meeting_date.isoformat() if meeting.meeting_date else None,
                task_id,
            ],
            task_id=task_id,
        )
    except (OperationalError, RedisError) as error:
        logger.error(
            "Could not enqueue indexing for meeting %s (%s)",
            meeting.id,
            type(error).__name__,
        )
        repository.set_indexing_status(
            meeting.id,
            meeting.indexing_task_id,
            "failed",
            "Could not queue indexing. Ensure Redis is running.",
        )
    finally:
        redis_client.close()
    return repository.get(meeting.id)


def cleanup_meeting_vectors(
    meeting_id: int,
    settings: Settings,
) -> tuple[UUID | None, str | None]:
    if settings.indexing_mode == "celery":
        return enqueue_vector_cleanup(meeting_id, settings)

    try:
        collection = create_chroma_client(settings).get_or_create_collection(
            name="meeting_transcripts",
            metadata={"hnsw:space": "cosine"},
        )
        collection.delete(where={"meeting_id": meeting_id})
    except Exception as error:
        logger.exception("Local vector cleanup failed for meeting %s", meeting_id)
        return None, f"Local vector cleanup failed ({type(error).__name__})."
    return None, None


def enqueue_vector_cleanup(
    meeting_id: int,
    settings: Settings,
) -> tuple[UUID | None, str | None]:
    task_id = uuid4()
    task_id_value = str(task_id)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        redis_client.set(f"meeting-index-current:{meeting_id}", task_id_value)
        delete_meeting_vectors.apply_async(
            args=[meeting_id, task_id_value],
            task_id=task_id_value,
        )
    except (OperationalError, RedisError) as error:
        logger.error(
            "Could not enqueue vector cleanup for meeting %s (%s)",
            meeting_id,
            type(error).__name__,
        )
        return None, "Could not queue vector cleanup. Ensure Redis is running."
    finally:
        redis_client.close()
    return task_id, None


def get_meeting_index_status(
    meeting_id: int,
    task_id: UUID | None,
    stored_status: IndexingStatus,
    stored_error: str | None,
    settings: Settings,
) -> MeetingIndexStatusResponse:
    if task_id is None:
        return MeetingIndexStatusResponse(
            meeting_id=meeting_id,
            task_id=None,
            status="not_indexed",
        )

    error = stored_error
    status = stored_status
    if settings.indexing_mode == "celery" and stored_status in ("queued", "indexing"):
        try:
            result = AsyncResult(str(task_id), app=celery_app)
            task_state = result.state
        except (OperationalError, RedisError) as status_error:
            logger.warning(
                "Could not read indexing status for meeting %s (%s)",
                meeting_id,
                type(status_error).__name__,
            )
            error = "Could not read task status. Ensure Redis is running."
        else:
            if task_state == "STARTED":
                status = "indexing"
            elif task_state == "SUCCESS":
                status = "indexed"
            elif task_state == "FAILURE":
                status = "failed"

    if status == "failed" and error is None:
        logs = "Celery worker" if settings.indexing_mode == "celery" else "FastAPI"
        error = f"Indexing failed. Check {logs} logs."
    return MeetingIndexStatusResponse(
        meeting_id=meeting_id,
        task_id=task_id,
        status=status,
        error=error,
    )
