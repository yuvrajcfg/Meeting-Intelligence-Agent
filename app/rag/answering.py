from datetime import datetime
import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from redis.exceptions import RedisError

from app.config import Settings
from app.exceptions import MeetingNotFoundError
from app.repositories.protocols import MeetingRepository
from app.rag.components import (
    RAGDependencyError,
    create_chat_model,
    create_vector_store,
)
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

NO_ANSWER = "I couldn't find that information in the indexed meeting transcripts."

SMALL_TALK = {
    "hi": "Hello! How can I help you with your meeting transcripts today?",
    "hello": "Hi! Ask me anything about your indexed meetings.",
    "thanks": "You're welcome!",
    "thank you": "Happy to help!",
    "bye": "Goodbye! Have a great day.",
}

EVIDENCE_REQUEST_PHRASES = (
    "show evidence",
    "show the evidence",
    "show me the evidence",
    "show supporting evidence",
    "show the supporting evidence",
    "show supporting text",
    "show the supporting text",
    "show me the supporting text",
    "show source content",
    "show the source content",
    "show me the source content",
    "show source excerpt",
    "show the source excerpt",
    "show full transcript",
    "show the full transcript",
    "show full chunk",
    "show the full chunk",
)

SYSTEM_PROMPT = """You are a Meeting Intelligence Assistant.

Your job is to answer questions about meeting transcripts using only retrieved transcript evidence.

========================
GROUNDING RULES
========================

- Use retrieved transcript chunks only as evidence.
- Never use outside knowledge.
- Never invent facts, dates, speakers, decisions, actions, or conclusions.
- If the answer is not supported by the retrieved sources, respond exactly:

I couldn't find that information in the meeting transcripts.

========================
RESPONSE RULES
========================

- Summarize retrieved information in your own words.
- Do not copy transcript sentences.
- Do not quote transcript text unless the user explicitly asks for a quote.
- Keep answers concise and factual.
- Do not include information that is not directly supported by the retrieved context.
- Avoid speculation, interpretation, assumptions, and opinion.

========================
PRIVACY RULES
========================

- Do not reveal transcript text verbatim.
- Do not return large excerpts from transcripts.
- Do not expose raw chunk content.
- Do not mention speaker names unless the user explicitly asks:
  - Who said it?
  - Which participant mentioned this?
  - When was this discussed?

========================
SOURCE USAGE RULES
========================

- Every factual statement must be supported by at least one source citation.
- Use citations in the format [S1], [S2], etc.
- Do not cite sources that were not actually used.
- Multiple citations may be provided when information comes from multiple chunks.
- After the answer, always include a Sources section.
- Each source must be displayed using the following format:

[S1] | <MEETING TITLE> | <SPEAKER NAME IF AVAILABLE> | <TIMESTAMP IF AVAILABLE>

Examples:

[S1] | Sprint Planning Meeting | Yuvraj Singh | 00:05:12
[S2] | Meeting Transcript 1 | Sarthak | 00:17:45
[S3] | Quarterly Review | Speaker Not Specified | Timestamp Not Available

- Never invent meeting titles, speaker names, or timestamps.
- Only display a speaker name if it is explicitly present in the cited transcript chunk.
- Only display a timestamp if it is explicitly present in the cited transcript chunk.
- If speaker information is unavailable, display:
  Speaker Not Specified

- If timestamp information is unavailable, display:
  Timestamp Not Available

- If meeting title metadata is unavailable, display:
  Meeting Title Not Available

- Sources must always appear at the end of the response.

Example Response:

Answer:
The meeting focused on reviewing project progress and planning future implementation activities. [S1]

Sources:
[S1] | Meeting Transcript 1 | Speaker Not Specified | 00:01:22

========================
WHEN QUESTIONS ASK FOR DETAILS
========================

For questions such as:

- What was discussed?
- What was the objective?
- What decisions were made?
- What action items were assigned?

Provide a concise summary rather than transcript wording.

Example:

Bad:
"The objective was to review our progress on the Meeting Intelligence Agent project."

Good:
"The meeting focused on reviewing project progress and planning upcoming implementation work. [S1]"

========================
SPEAKER RULES
========================

Only identify speakers when:

1. The transcript explicitly identifies a speaker.
2. The user explicitly requests speaker information.

Otherwise refer to:
- a participant
- a team member
- an attendee

========================
TIMESTAMP RULES
========================

Only provide timestamps if:
- They exist in the cited transcript chunk.
- The user explicitly requests timing information.

Never infer timestamps.

========================
OUTPUT STYLE
========================

- Professional
- Concise
- Evidence-based
- No transcript leakage
- No hallucinations

Always answer using the retrieved sources as evidence."""


def _format_date(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "not specified"


def _metadata_text(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metadata_chunk_index(metadata: Mapping[str, Any]) -> int | None:
    value = metadata.get("chunk_index")
    if value is None:
        value = metadata.get("chunk_id")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _metadata_timestamp(metadata: Mapping[str, Any]) -> str | None:
    timestamp = _metadata_text(metadata, "timestamp")
    if timestamp:
        return timestamp
    start = _metadata_text(metadata, "start_timestamp", "start_time")
    end = _metadata_text(metadata, "end_timestamp", "end_time")
    if start and end:
        return f"{start} - {end}"
    return start or end


def _requests_evidence(question: str) -> bool:
    normalized = " ".join(question.casefold().split())
    return any(phrase in normalized for phrase in EVIDENCE_REQUEST_PHRASES)


def answer_question(
    *,
    request: ChatRequest,
    repository: MeetingRepository,
    settings: Settings,
) -> ChatResponse:
    small_talk_answer = SMALL_TALK.get(request.question.lower().strip())
    if small_talk_answer is not None:
        prompt = (
            f'The user said: "{request.question}"\n'
            "Reply with exactly the suggested response below. Do not add any "
            f"other text:\n{small_talk_answer}"
        )
        answer = create_chat_model(settings).invoke(prompt)
        return ChatResponse(answer=answer, sources=[])

    vector_store = create_vector_store(settings)
    retrieved = vector_store.similarity_search(request.question, k=4)
    sources: list[ChatSource] = []
    context_sections: list[str] = []
    include_evidence = _requests_evidence(request.question)

    for document in retrieved:
        meeting_id = int(document.metadata["meeting_id"])
        try:
            meeting = repository.get(meeting_id)
        except MeetingNotFoundError:
            continue
        if str(meeting.indexing_task_id) != document.metadata.get("indexing_task_id"):
            continue
        if meeting.indexing_status not in ("indexed", "queued", "indexing"):
            continue
        if meeting.indexing_status != "indexed":
            if settings.indexing_mode != "celery":
                continue
            try:
                task_state = celery_app.AsyncResult(
                    str(meeting.indexing_task_id)
                ).state
            except RedisError as error:
                logger.warning(
                    "Could not check task status for meeting %s (%s)",
                    meeting.id,
                    type(error).__name__,
                )
                raise RAGDependencyError(
                    "Redis is unavailable, so meeting indexing status cannot be "
                    "verified. Check REDIS_URL and the Redis service."
                ) from error
            if task_state != "SUCCESS":
                continue

        source_id = f"S{len(sources) + 1}"
        metadata = document.metadata
        transcript_name = (
            _metadata_text(metadata, "transcript_name", "meeting_title")
            or meeting.title
        )
        sources.append(
            ChatSource(
                source_id=source_id,
                meeting_id=meeting.id,
                meeting_title=transcript_name,
                meeting_date=meeting.meeting_date,
                chunk_index=_metadata_chunk_index(metadata),
                speaker_name=_metadata_text(metadata, "speaker_name", "speaker"),
                timestamp=_metadata_timestamp(metadata),
                excerpt=document.page_content if include_evidence else None,
            )
        )
        context_sections.append(
            f"[{source_id}] Meeting: {meeting.title}\n"
            f"Meeting date: {_format_date(meeting.meeting_date)}\n"
            f"Transcript excerpt:\n{document.page_content}"
        )

    if not sources:
        return ChatResponse(answer=NO_ANSWER, sources=[])

    history = [
        HumanMessage(content=message.content)
        if message.role == "user"
        else AIMessage(content=message.content)
        for message in request.history[-8:]
    ]
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            (
                "human",
                "Retrieved sources:\n{context}\n\nQuestion: {question}",
            ),
        ]
    )
    chain = prompt | create_chat_model(settings) | StrOutputParser()
    answer = chain.invoke(
        {
            "context": "\n\n".join(context_sections),
            "question": request.question,
            "history": history,
        }
    )
    return ChatResponse(answer=answer, sources=sources)
