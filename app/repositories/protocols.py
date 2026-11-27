from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.schemas.meeting import (
    MeetingCreate,
    MeetingDeleteResponse,
    MeetingIndexSummary,
    IndexingStatus,
    MeetingResponse,
    MeetingUploadMetadata,
    MeetingUpdate,
)


class MeetingRepository(Protocol):
    def create(
        self,
        meeting: MeetingCreate,
        indexing_task_id: UUID,
    ) -> MeetingResponse: ...

    def list(
        self,
        *,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingResponse], int]: ...

    def list_index_status(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingIndexSummary], int]: ...

    def get(self, meeting_id: int) -> MeetingResponse: ...

    def update(
        self,
        meeting_id: int,
        meeting: MeetingUpdate,
        indexing_task_id: UUID,
    ) -> MeetingResponse: ...

    def delete(self, meeting_id: int) -> MeetingDeleteResponse: ...

    def queue_indexing(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
    ) -> MeetingResponse: ...

    def set_upload_metadata(
        self,
        meeting_id: int,
        metadata: MeetingUploadMetadata,
    ) -> None: ...

    def set_indexing_status(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
        status: IndexingStatus,
        error: str | None = None,
        *,
        indexed_at: datetime | None = None,
        chunk_count: int | None = None,
    ) -> None: ...
