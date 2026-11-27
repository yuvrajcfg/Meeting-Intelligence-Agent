from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ] = Field(description="A question about the meeting transcripts.")


class AskResponse(BaseModel):
    answer: str
    sources: list[str] = Field(
        default_factory=list,
        description="Compact source metadata, with transcript evidence when requested.",
    )
