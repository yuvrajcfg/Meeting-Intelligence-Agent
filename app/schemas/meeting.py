from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IndexingStatus = Literal[
    "not_indexed",
    "pending",
    "processing",
    "ready",
    "failed",
]

MeetingTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
TranscriptText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000_000),
]


class MeetingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: MeetingTitle
    transcript: TranscriptText
    meeting_date: datetime | None = None


class MeetingUpdate(MeetingCreate):
    pass


class MeetingUploadMetadata(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=20)
    file_size: int = Field(ge=0)
    uploaded_at: datetime
    original_file_path: str = Field(min_length=1, max_length=1000)
    cleaned_text_path: str = Field(min_length=1, max_length=1000)
    chroma_collection: str = Field(min_length=1, max_length=100)


class MeetingResponse(BaseModel):
    id: int = Field(gt=0)
    title: str
    transcript: str
    meeting_date: datetime | None
    created_at: datetime
    updated_at: datetime
    indexing_task_id: UUID | None = None
    indexing_status: IndexingStatus = "not_indexed"
    status: IndexingStatus = "not_indexed"
    indexing_error: str | None = None
    error_message: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    file_size: int | None = Field(default=None, ge=0)
    uploaded_at: datetime | None = None
    indexed_at: datetime | None = None
    chunk_count: int | None = Field(default=None, ge=0)
    original_file_path: str | None = None
    cleaned_text_path: str | None = None
    chroma_collection: str | None = None


class MeetingIndexStatusResponse(BaseModel):
    meeting_id: int = Field(gt=0)
    task_id: UUID | None = None
    status: IndexingStatus
    error: str | None = None


class MeetingIndexSummary(BaseModel):
    meeting_id: int = Field(gt=0)
    title: str
    meeting_date: datetime | None
    indexing_task_id: UUID | None
    indexing_status: IndexingStatus
    indexing_error: str | None = None


class MeetingIndexSummaryListResponse(BaseModel):
    items: list[MeetingIndexSummary]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)


class MeetingDeleteResponse(BaseModel):
    id: int = Field(gt=0)
    title: str
    message: str
    vector_cleanup_task_id: UUID | None = None
    vector_cleanup_status: Literal[
        "not_requested",
        "queued",
        "deleted",
        "failed",
    ] = "not_requested"
    vector_cleanup_error: str | None = None


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
