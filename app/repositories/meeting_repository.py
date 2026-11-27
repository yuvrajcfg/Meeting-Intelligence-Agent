from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import UUID

from app.exceptions import MeetingNotFoundError
from app.schemas.meeting import (
    MeetingCreate,
    MeetingDeleteResponse,
    MeetingIndexSummary,
    IndexingStatus,
    MeetingResponse,
    MeetingUpdate,
)


class InMemoryMeetingRepository:
    def __init__(self) -> None:
        self._meetings: dict[int, MeetingResponse] = {}
        self._next_id = 1
        self._lock = Lock()

    def create(
        self,
        meeting: MeetingCreate,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        now = datetime.now(timezone.utc)
        with self._lock:
            record = MeetingResponse(
                id=self._next_id,
                created_at=now,
                updated_at=now,
                indexing_task_id=indexing_task_id,
                indexing_status="queued",
                **meeting.model_dump(),
            )
            self._next_id += 1
            self._meetings[record.id] = record
        return record

    def list(
        self,
        *,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingResponse], int]:
        with self._lock:
            meetings = list(self._meetings.values())

        if search is not None:
            search_term = search.casefold()
            meetings = [
                meeting
                for meeting in meetings
                if search_term in meeting.title.casefold()
                or search_term in meeting.transcript.casefold()
            ]

        meetings.sort(key=lambda meeting: meeting.created_at, reverse=True)
        total = len(meetings)
        return meetings[offset : offset + limit], total

    def get(self, meeting_id: int) -> MeetingResponse:
        with self._lock:
            meeting = self._meetings.get(meeting_id)
        if meeting is None:
            raise MeetingNotFoundError(meeting_id)
        return meeting

    def list_index_status(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingIndexSummary], int]:
        with self._lock:
            meetings = sorted(
                self._meetings.values(),
                key=lambda meeting: meeting.created_at,
                reverse=True,
            )
        total = len(meetings)
        items = [
            MeetingIndexSummary(
                meeting_id=meeting.id,
                title=meeting.title,
                meeting_date=meeting.meeting_date,
                indexing_task_id=meeting.indexing_task_id,
                indexing_status=meeting.indexing_status,
                indexing_error=meeting.indexing_error,
            )
            for meeting in meetings[offset : offset + limit]
        ]
        return items, total

    def update(
        self,
        meeting_id: int,
        meeting: MeetingUpdate,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        with self._lock:
            existing = self._meetings.get(meeting_id)
            if existing is None:
                raise MeetingNotFoundError(meeting_id)

            updated = MeetingResponse(
                id=existing.id,
                created_at=existing.created_at,
                updated_at=datetime.now(timezone.utc),
                indexing_task_id=indexing_task_id,
                indexing_status="queued",
                indexing_error=None,
                **meeting.model_dump(),
            )
            self._meetings[meeting_id] = updated
        return updated

    def queue_indexing(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        with self._lock:
            meeting = self._meetings.get(meeting_id)
            if meeting is None:
                raise MeetingNotFoundError(meeting_id)
            queued = meeting.model_copy(
                update={
                    "indexing_task_id": indexing_task_id,
                    "indexing_status": "queued",
                    "indexing_error": None,
                }
            )
            self._meetings[meeting_id] = queued
        return queued

    def set_indexing_status(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
        status: IndexingStatus,
        error: str | None = None,
    ) -> None:
        with self._lock:
            meeting = self._meetings.get(meeting_id)
            if meeting is None or meeting.indexing_task_id != indexing_task_id:
                return
            self._meetings[meeting_id] = meeting.model_copy(
                update={"indexing_status": status, "indexing_error": error}
            )

    def delete(self, meeting_id: int) -> MeetingDeleteResponse:
        with self._lock:
            meeting = self._meetings.pop(meeting_id, None)
        if meeting is None:
            raise MeetingNotFoundError(meeting_id)
        return MeetingDeleteResponse(
            id=meeting.id,
            title=meeting.title,
            message=f"Meeting '{meeting.title}' (ID {meeting.id}) deleted successfully.",
        )
