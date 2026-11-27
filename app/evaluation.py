import argparse
import json
import re
from pathlib import Path
from typing import Annotated

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.config import Settings, get_settings
from app.rag.answering import answer_question
from app.rag.components import create_vector_store
from app.repositories.meeting_repository import InMemoryMeetingRepository
from app.schemas.chat import ChatRequest

EvaluationQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: EvaluationQuery
    relevant_chunk_ids: list[str] = Field(min_length=1)


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=4, ge=1, le=100)
    cases: list[EvaluationCase] = Field(min_length=1)


def _chunk_id(document: Document) -> str | None:
    meeting_id = document.metadata.get("meeting_id")
    chunk_index = document.metadata.get("chunk_index")
    if not isinstance(meeting_id, int) or not isinstance(chunk_index, int):
        return None
    return f"meeting-{meeting_id}-chunk-{chunk_index}"


def evaluate_dataset(
    dataset: EvaluationDataset,
    *,
    settings: Settings,
) -> dict[str, object]:
    vector_store = create_vector_store(settings)
    repository = InMemoryMeetingRepository()
    case_results: list[dict[str, object]] = []

    for case in dataset.cases:
        documents = vector_store.similarity_search(case.query, k=dataset.top_k)
        retrieved_ids = [
            chunk_id
            for document in documents
            if (chunk_id := _chunk_id(document)) is not None
        ]
        relevant_ids = set(case.relevant_chunk_ids)
        retrieved_relevant = relevant_ids.intersection(retrieved_ids)
        first_relevant_rank = next(
            (
                rank
                for rank, chunk_id in enumerate(retrieved_ids, start=1)
                if chunk_id in relevant_ids
            ),
            None,
        )

        answer = answer_question(
            request=ChatRequest(question=case.query),
            repository=repository,
            settings=settings,
            retrieved_documents=documents,
        )
        source_by_id = {
            source.source_id: (
                f"meeting-{source.meeting_id}-chunk-{source.chunk_index}"
                if source.chunk_index is not None
                else None
            )
            for source in answer.sources
        }
        cited_source_ids = re.findall(r"\[(S\d+)\]", answer.answer)
        cited_chunk_ids = [
            source_by_id[source_id]
            for source_id in cited_source_ids
            if source_id in source_by_id and source_by_id[source_id] is not None
        ]
        cited_relevant = relevant_ids.intersection(cited_chunk_ids)
        relevant_citation_count = sum(
            source_by_id.get(source_id) in relevant_ids
            for source_id in cited_source_ids
        )

        case_results.append(
            {
                "query": case.query,
                "retrieved_chunk_ids": retrieved_ids,
                "cited_chunk_ids": cited_chunk_ids,
                "precision_at_k": len(retrieved_relevant) / dataset.top_k,
                "recall_at_k": len(retrieved_relevant) / len(relevant_ids),
                "reciprocal_rank": (
                    1 / first_relevant_rank if first_relevant_rank else 0.0
                ),
                "hit": bool(retrieved_relevant),
                "citation_precision": (
                    relevant_citation_count / len(cited_source_ids)
                    if cited_source_ids
                    else 0.0
                ),
                "citation_recall": len(cited_relevant) / len(relevant_ids),
            }
        )

    def mean(metric: str) -> float:
        return sum(float(case[metric]) for case in case_results) / len(case_results)

    return {
        "top_k": dataset.top_k,
        "query_count": len(case_results),
        "metrics": {
            "precision_at_k": mean("precision_at_k"),
            "recall_at_k": mean("recall_at_k"),
            "mrr_at_k": mean("reciprocal_rank"),
            "hit_rate_at_k": mean("hit"),
            "citation_precision": mean("citation_precision"),
            "citation_recall": mean("citation_recall"),
        },
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate transcript retrieval and source citations."
    )
    parser.add_argument("dataset", type=Path, help="Path to the evaluation JSON file.")
    arguments = parser.parse_args()
    with arguments.dataset.open(encoding="utf-8") as dataset_file:
        dataset = EvaluationDataset.model_validate(json.load(dataset_file))
    result = evaluate_dataset(dataset, settings=get_settings())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
