from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, Row, URL

from app.exceptions import MeetingNotFoundError
from app.schemas.meeting import (
    IndexingStatus,
    MeetingCreate,
    MeetingDeleteResponse,
    MeetingIndexSummary,
    MeetingResponse,
    MeetingUpdate,
)


class SqlServerMeetingRepository:
    def __init__(self, connection_string: str) -> None:
        url = URL.create(
            "mssql+pyodbc",
            query={"odbc_connect": connection_string},
        )
        self._engine: Engine = create_engine(url, pool_pre_ping=True)

    @staticmethod
    def _to_meeting(row: Row[Any]) -> MeetingResponse:
        values = row._mapping
        return MeetingResponse(
            id=values["MeetingId"],
            title=values["Title"],
            transcript=values["Transcript"],
            meeting_date=values["MeetingDate"],
            created_at=values["CreatedAt"],
            updated_at=values["UpdatedAt"],
            indexing_task_id=values["IndexingTaskId"],
            indexing_status=values["IndexingStatus"],
            indexing_error=values["IndexingError"],
        )

    def check_connection(self) -> None:
        with self._engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1").scalar_one()

    def close(self) -> None:
        self._engine.dispose()

    def create(
        self,
        meeting: MeetingCreate,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        with self._engine.begin() as connection:
            row = connection.exec_driver_sql(
                "EXEC dbo.Meeting_Create ?, ?, ?, ?",
                (
                    meeting.title,
                    meeting.transcript,
                    str(indexing_task_id),
                    meeting.meeting_date,
                ),
            ).first()
        if row is None:
            raise RuntimeError("Meeting_Create did not return the created meeting.")
        return self._to_meeting(row)

    def list(
        self,
        *,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingResponse], int]:
        with self._engine.begin() as connection:
            total = int(
                connection.exec_driver_sql(
                    "EXEC dbo.Meeting_Count ?",
                    (search,),
                ).scalar_one()
            )
            result = connection.exec_driver_sql(
                "EXEC dbo.Meeting_List ?, ?, ?",
                (search, offset, limit),
            )
            items = [self._to_meeting(row) for row in result.fetchall()]
        return items, total

    def get(self, meeting_id: int) -> MeetingResponse:
        with self._engine.begin() as connection:
            row = connection.exec_driver_sql(
                "EXEC dbo.Meeting_Get ?",
                (meeting_id,),
            ).first()
        if row is None:
            raise MeetingNotFoundError(meeting_id)
        return self._to_meeting(row)

    def list_index_status(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[MeetingIndexSummary], int]:
        with self._engine.begin() as connection:
            total = int(
                connection.exec_driver_sql(
                    "EXEC dbo.Meeting_Count ?",
                    (None,),
                ).scalar_one()
            )
            result = connection.exec_driver_sql(
                "EXEC dbo.Meeting_ListIndexStatus ?, ?",
                (offset, limit),
            )
            items = [
                MeetingIndexSummary(
                    meeting_id=row._mapping["MeetingId"],
                    title=row._mapping["Title"],
                    meeting_date=row._mapping["MeetingDate"],
                    indexing_task_id=row._mapping["IndexingTaskId"],
                    indexing_status=row._mapping["IndexingStatus"],
                    indexing_error=row._mapping["IndexingError"],
                )
                for row in result.fetchall()
            ]
        return items, total

    def update(
        self,
        meeting_id: int,
        meeting: MeetingUpdate,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        with self._engine.begin() as connection:
            row = connection.exec_driver_sql(
                "EXEC dbo.Meeting_Update ?, ?, ?, ?, ?",
                (
                    meeting_id,
                    meeting.title,
                    meeting.transcript,
                    str(indexing_task_id),
                    meeting.meeting_date,
                ),
            ).first()
        if row is None:
            raise MeetingNotFoundError(meeting_id)
        return self._to_meeting(row)

    def queue_indexing(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
    ) -> MeetingResponse:
        with self._engine.begin() as connection:
            row = connection.exec_driver_sql(
                "EXEC dbo.Meeting_QueueIndexing ?, ?",
                (meeting_id, str(indexing_task_id)),
            ).first()
        if row is None:
            raise MeetingNotFoundError(meeting_id)
        return self._to_meeting(row)

    def set_indexing_status(
        self,
        meeting_id: int,
        indexing_task_id: UUID,
        status: IndexingStatus,
        error: str | None = None,
    ) -> None:
        with self._engine.begin() as connection:
            connection.exec_driver_sql(
                "EXEC dbo.Meeting_SetIndexingStatus ?, ?, ?, ?",
                (meeting_id, str(indexing_task_id), status, error),
            )

    def delete(self, meeting_id: int) -> MeetingDeleteResponse:
        with self._engine.begin() as connection:
            row = connection.exec_driver_sql(
                "EXEC dbo.Meeting_Delete ?",
                (meeting_id,),
            ).first()
        if row is None:
            raise MeetingNotFoundError(meeting_id)
        values = row._mapping
        meeting_id = values["MeetingId"]
        title = values["Title"]
        return MeetingDeleteResponse(
            id=meeting_id,
            title=title,
            message=f"Meeting '{title}' (ID {meeting_id}) deleted successfully.",
        )
