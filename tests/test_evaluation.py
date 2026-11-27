import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from app.config import Settings
from app.evaluation import EvaluationDataset, evaluate_dataset
from app.schemas.chat import ChatResponse, ChatSource


class RetrievalEvaluationTests(unittest.TestCase):
    def test_dataset_evaluation_reports_retrieval_and_citation_metrics(self) -> None:
        settings = Settings(_env_file=None)
        dataset = EvaluationDataset.model_validate(
            {
                "top_k": 2,
                "cases": [
                    {
                        "query": "Who owns the action?",
                        "relevant_chunk_ids": [
                            "meeting-1-chunk-2",
                            "meeting-1-chunk-3",
                        ],
                    }
                ],
            }
        )
        documents = [
            Document(
                page_content="Relevant passage.",
                metadata={"meeting_id": 1, "chunk_index": 2},
            ),
            Document(
                page_content="Other passage.",
                metadata={"meeting_id": 1, "chunk_index": 5},
            ),
        ]
        response = ChatResponse(
            answer="The action belongs to the project lead [S1].",
            sources=[
                ChatSource(
                    source_id="S1",
                    meeting_id=1,
                    meeting_title="Planning",
                    meeting_date=None,
                    chunk_index=2,
                ),
                ChatSource(
                    source_id="S2",
                    meeting_id=1,
                    meeting_title="Planning",
                    meeting_date=None,
                    chunk_index=5,
                ),
            ],
        )
        with (
            patch("app.evaluation.create_vector_store") as create_vector_store,
            patch("app.evaluation.answer_question", return_value=response) as answer,
        ):
            create_vector_store.return_value.similarity_search.return_value = documents
            result = evaluate_dataset(dataset, settings=settings)

        answer.assert_called_once()
        self.assertEqual(
            answer.call_args.kwargs["retrieved_documents"],
            documents,
        )
        self.assertEqual(
            result["metrics"],
            {
                "precision_at_k": 0.5,
                "recall_at_k": 0.5,
                "mrr_at_k": 1.0,
                "hit_rate_at_k": 1.0,
                "citation_precision": 1.0,
                "citation_recall": 0.5,
            },
        )


if __name__ == "__main__":
    unittest.main()
