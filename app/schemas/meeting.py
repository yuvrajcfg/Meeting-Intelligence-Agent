from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IndexingStatus = Literal[
    "not_indexed",
    "queued",
    "indexing",
    "indexed",
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


class MeetingResponse(BaseModel):
    id: int = Field(gt=0)
    title: str
    transcript: str
    meeting_date: datetime | None
    created_at: datetime
    updated_at: datetime
    indexing_task_id: UUID | None = None
    indexing_status: IndexingStatus = "not_indexed"
    indexing_error: str | None = None


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
