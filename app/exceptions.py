class MeetingNotFoundError(Exception):
    def __init__(self, meeting_id: int) -> None:
        self.meeting_id = meeting_id
        super().__init__(f"Meeting '{meeting_id}' was not found.")
