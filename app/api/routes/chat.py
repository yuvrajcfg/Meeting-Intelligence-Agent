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
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "LLM or embedding endpoint settings are missing."
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "The LLM or embedding provider returned an error."
        },
    },
)
def chat(
    request: ChatRequest,
    repository: MeetingRepository = Depends(get_meeting_repository),
) -> ChatResponse:
    try:
        return answer_question(
            request=request,
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
