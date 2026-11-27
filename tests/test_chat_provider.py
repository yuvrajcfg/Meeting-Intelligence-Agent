import unittest
from unittest.mock import Mock, patch

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import SecretStr

from app.config import Settings
from app.rag.components import CustomLLM, RAGProviderError, create_chat_model


class CustomLLMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = CustomLLM(
            model="meeting-model",
            endpoint_url="https://provider.test/custom/complete-endpoint",
            api_key=SecretStr("test-key"),
            temperature=0.5,
            top_p=0.9,
            max_tokens=1000,
        )

    def test_posts_to_exact_url_and_provider_payload(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": "Grounded answer"}}]
        }
        response.raise_for_status.return_value = None

        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ) as post:
            answer = self.llm.invoke("Question", stop=["END"])

        self.assertEqual(answer, "Grounded answer")
        post.assert_called_once_with(
            "https://provider.test/custom/complete-endpoint",
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": "test-key",
            },
            json={
                "model": "meeting-model",
                "messages": [{"role": "user", "content": "Question"}],
                "temperature": 0.5,
                "top_p": 0.9,
                "max_tokens": 1000,
                "stop": ["END"],
            },
            timeout=(5, 60),
        )

    def test_factory_uses_configured_url_verbatim(self) -> None:
        endpoint_url = "https://provider.test/v2/chat/completions?mode=custom"
        settings = Settings(
            _env_file=None,
            llm_api_key=SecretStr("test-key"),
            llm_base_url=endpoint_url,
            llm_model="meeting-model",
        )
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": "Answer"}}]
        }
        response.raise_for_status.return_value = None
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ) as post:
            create_chat_model(settings).invoke("Question")

        self.assertEqual(post.call_args.args[0], endpoint_url)

    def test_chat_prompt_pipeline_invokes_custom_llm(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": "Grounded answer"}}]
        }
        response.raise_for_status.return_value = None
        chain = (
            ChatPromptTemplate.from_messages(
                [("system", "Use the sources."), ("human", "{question}")]
            )
            | self.llm
            | StrOutputParser()
        )

        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ) as post:
            answer = chain.invoke({"question": "What was decided?"})

        self.assertEqual(answer, "Grounded answer")
        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("Use the sources.", prompt)
        self.assertIn("What was decided?", prompt)

    def test_surfaces_provider_404(self) -> None:
        response = Mock(status_code=404)
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(RAGProviderError, "HTTP 404"):
                self.llm.invoke("Question")

    def test_rejects_malformed_response(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"choices": []}
        response.raise_for_status.return_value = None
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(RAGProviderError, "first choice"):
                self.llm.invoke("Question")


if __name__ == "__main__":
    unittest.main()
