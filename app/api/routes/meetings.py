from pathlib import Path as FilePath
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.dependencies import get_meeting_repository
from app.config import get_settings
from app.repositories.protocols import MeetingRepository as MeetingRepositoryProtocol
from app.services.indexing import (
    cleanup_meeting_vectors,
    get_meeting_index_status,
    start_meeting_index,
)
from app.services.transcripts import (
    MAX_UPLOAD_BYTES,
    TranscriptExtractionError,
    UnsupportedTranscriptFormatError,
    extract_transcript,
)
from app.schemas.meeting import (
    MeetingCreate,
    MeetingDeleteResponse,
    MeetingIndexStatusResponse,
    MeetingIndexSummaryListResponse,
    MeetingListResponse,
    MeetingResponse,
    MeetingUpdate,
)

router = APIRouter(prefix="/meetings")
RepositoryDependency = Annotated[
    MeetingRepositoryProtocol,
    Depends(get_meeting_repository),
]


@router.post(
    "",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting(
    meeting: MeetingCreate,
    repository: RepositoryDependency,
) -> MeetingResponse:
    record = repository.create(meeting, uuid4())
    return start_meeting_index(repository, record, get_settings())


@router.post(
    "/upload",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_meeting(
    repository: RepositoryDependency,
    file: Annotated[UploadFile, File(...)],
) -> MeetingResponse:
    filename = file.filename or ""
    title = FilePath(filename).stem.strip()
    if not title or len(title) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded filename must produce a title of 1 to 200 characters.",
        )

    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Uploaded files must be 10 MB or smaller.",
            )
        try:
            transcript = extract_transcript(filename, content)
        except UnsupportedTranscriptFormatError as error:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(error),
            ) from error
        except TranscriptExtractionError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
    finally:
        await file.close()

    meeting = MeetingCreate(
        title=title,
        transcript=transcript,
    )
    record = repository.create(meeting, uuid4())
    return start_meeting_index(repository, record, get_settings())


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    repository: RepositoryDependency,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MeetingListResponse:
    items, total = repository.list(search=search, offset=offset, limit=limit)
    return MeetingListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/index-status",
    response_model=MeetingIndexSummaryListResponse,
)
def list_meeting_index_status(
    repository: RepositoryDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MeetingIndexSummaryListResponse:
    items, total = repository.list_index_status(offset=offset, limit=limit)
    settings = get_settings()
    resolved_items = []
    for item in items:
        status_response = get_meeting_index_status(
            item.meeting_id,
            item.indexing_task_id,
            item.indexing_status,
            item.indexing_error,
            settings,
        )
        resolved_items.append(
            item.model_copy(
                update={
                    "indexing_status": status_response.status,
                    "indexing_error": status_response.error,
                }
            )
        )
    items = resolved_items
    return MeetingIndexSummaryListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(
    meeting_id: Annotated[int, Path(ge=1)],
    repository: RepositoryDependency,
) -> MeetingResponse:
    return repository.get(meeting_id)


@router.get(
    "/{meeting_id}/index-status",
    response_model=MeetingIndexStatusResponse,
)
def get_meeting_indexing_status(
    meeting_id: Annotated[int, Path(ge=1)],
    repository: RepositoryDependency,
) -> MeetingIndexStatusResponse:
    meeting = repository.get(meeting_id)
    return get_meeting_index_status(
        meeting.id,
        meeting.indexing_task_id,
        meeting.indexing_status,
        meeting.indexing_error,
        get_settings(),
    )


@router.post(
    "/{meeting_id}/index",
    response_model=MeetingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_meeting(
    meeting_id: Annotated[int, Path(ge=1)],
    repository: RepositoryDependency,
    response: Response,
) -> MeetingResponse:
    record = repository.queue_indexing(meeting_id, uuid4())
    settings = get_settings()
    result = start_meeting_index(repository, record, settings)
    if settings.indexing_mode == "local":
        response.status_code = status.HTTP_200_OK
    return result


@router.put("/{meeting_id}", response_model=MeetingResponse)
def update_meeting(
    meeting_id: Annotated[int, Path(ge=1)],
    meeting: MeetingUpdate,
    repository: RepositoryDependency,
) -> MeetingResponse:
    record = repository.update(meeting_id, meeting, uuid4())
    return start_meeting_index(repository, record, get_settings())


@router.delete(
    "/{meeting_id}",
    response_model=MeetingDeleteResponse,
)
def delete_meeting(
    meeting_id: Annotated[int, Path(ge=1)],
    repository: RepositoryDependency,
) -> MeetingDeleteResponse:
    deleted = repository.delete(meeting_id)
    settings = get_settings()
    task_id, error = cleanup_meeting_vectors(meeting_id, settings)
    return deleted.model_copy(
        update={
            "vector_cleanup_task_id": task_id,
            "vector_cleanup_status": (
                "failed"
                if error
                else "queued"
                if settings.indexing_mode == "celery"
                else "deleted"
            ),
            "vector_cleanup_error": error,
        }
    )
