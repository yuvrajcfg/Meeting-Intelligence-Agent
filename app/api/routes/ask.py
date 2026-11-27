from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_meeting_repository
from app.config import get_settings
from app.rag.answering import answer_question
from app.rag.components import (
    RAGConfigurationError,
    RAGDependencyError,
    RAGProviderError,
)
from app.repositories.protocols import MeetingRepository
from app.schemas.ask import AskRequest, AskResponse
from app.schemas.chat import ChatRequest

router = APIRouter()


@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "LLM or embedding endpoint settings are missing."
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "The LLM or embedding provider returned an error."
        },
    },
)
def ask_question(
    request: AskRequest,
    repository: MeetingRepository = Depends(get_meeting_repository),
) -> AskResponse:
    try:
        response = answer_question(
            request=ChatRequest(question=request.question),
            repository=repository,
            settings=get_settings(),
        )
    except RAGConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except RAGDependencyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except RAGProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    sources = []
    for source in response.sources:
        source_fields = [f"[{source.source_id}] {source.meeting_title}"]
        if source.chunk_index is not None:
            source_fields.append(f"Chunk {source.chunk_index}")
        if source.speaker_name:
            source_fields.append(source.speaker_name)
        if source.timestamp:
            source_fields.append(source.timestamp)
        source_text = " | ".join(source_fields)
        if source.excerpt is not None:
            source_text = f"{source_text}\nEvidence: {source.excerpt}"
        sources.append(source_text)
    return AskResponse(answer=response.answer, sources=sources)
