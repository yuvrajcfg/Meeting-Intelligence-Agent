import unittest
from unittest.mock import Mock, patch

from app.config import Settings
from app.rag.answering import NO_ANSWER, SMALL_TALK, answer_question
from app.repositories.protocols import MeetingRepository
from app.schemas.chat import ChatRequest


class SmallTalkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock(spec=MeetingRepository)
        self.settings = Settings(_env_file=None)

    def test_exact_small_talk_returns_fixed_response_without_retrieval(self) -> None:
        llm = Mock()
        llm.invoke.side_effect = list(SMALL_TALK.values())
        with (
            patch("app.rag.answering.create_vector_store") as create_vector_store,
            patch("app.rag.answering.create_chat_model", return_value=llm) as create_chat_model,
        ):
            for query, answer in SMALL_TALK.items():
                with self.subTest(query=query):
                    response = answer_question(
                        request=ChatRequest(question=f"  {query.upper()}  "),
                        repository=self.repository,
                        settings=self.settings,
                    )

                    self.assertEqual(response.answer, answer)
                    self.assertEqual(response.sources, [])

            create_vector_store.assert_not_called()
            self.assertEqual(create_chat_model.call_count, len(SMALL_TALK))
            for (query, expected_answer), call_args in zip(
                SMALL_TALK.items(),
                llm.invoke.call_args_list,
            ):
                prompt = call_args.args[0]
                self.assertIn(query, prompt.lower())
                self.assertIn(expected_answer, prompt)

    def test_other_questions_continue_through_retrieval(self) -> None:
        vector_store = Mock()
        vector_store.similarity_search.return_value = []
        with patch(
            "app.rag.answering.create_vector_store",
            return_value=vector_store,
        ) as create_vector_store:
            response = answer_question(
                request=ChatRequest(question="What deadlines were discussed?"),
                repository=self.repository,
                settings=self.settings,
            )

        create_vector_store.assert_called_once_with(self.settings)
        vector_store.similarity_search.assert_called_once_with(
            "What deadlines were discussed?",
            k=4,
        )
        self.assertEqual(response.answer, NO_ANSWER)
        self.assertEqual(response.sources, [])


if __name__ == "__main__":
    unittest.main()
