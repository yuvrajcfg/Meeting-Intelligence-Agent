from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ]
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=8)


class ChatSource(BaseModel):
    source_id: str
    meeting_id: int
    meeting_title: str
    meeting_date: datetime | None
    chunk_index: int | None = Field(default=None, ge=0)
    speaker_name: str | None = None
    timestamp: str | None = None
    excerpt: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)


