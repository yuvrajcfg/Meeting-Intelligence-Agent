from fastapi import Request

from app.repositories.protocols import MeetingRepository


def get_meeting_repository(request: Request) -> MeetingRepository:
    return request.app.state.meeting_repository
