import unittest
from unittest.mock import Mock, call, patch

from pydantic import SecretStr

from app.config import Settings
from app.rag.components import (
    CustomEmbeddings,
    RAGProviderError,
    create_embeddings,
)


class CustomEmbeddingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.embeddings = CustomEmbeddings(
            api_key="test-key",
            endpoint_url="https://provider.test/v3/text/embeddings",
            dimensions=736,
        )

    def test_posts_each_text_and_preserves_response_order(self) -> None:
        def make_response(
            _url: str,
            *,
            json: dict[str, object],
            **_kwargs: object,
        ) -> Mock:
            del _url, _kwargs
            texts = json["texts"]
            if not isinstance(texts, list):
                raise AssertionError("provider payload must contain a text list")
            response = Mock(status_code=200)
            response.json.return_value = {
                "embeddings": [float(int(str(texts[0])[1:]))] * 736,
                "usage": {"input_tokens": 1},
            }
            response.raise_for_status.return_value = None
            return response

        texts = ["t0", "t1"]
        with patch(
            "app.rag.components.requests.post",
            side_effect=make_response,
        ) as post:
            result = self.embeddings.embed_documents(texts)

        self.assertEqual(len(result), len(texts))
        self.assertEqual(result[0], [0.0] * 736)
        self.assertEqual(result[1], [1.0] * 736)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            post.call_args_list[0],
            call(
                "https://provider.test/v3/text/embeddings",
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": "test-key",
                },
                json={"texts": ["t0"], "dimensions": 736},
                timeout=(5, 60),
            ),
        )
        self.assertEqual(
            post.call_args_list[1].kwargs["json"],
            {"texts": ["t1"], "dimensions": 736},
        )

    def test_embed_query_returns_provider_vector(self) -> None:
        vector = [0.5] * 736
        response = Mock(status_code=200)
        response.json.return_value = {
            "embeddings": vector,
            "usage": {"input_tokens": 1},
        }
        response.raise_for_status.return_value = None
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ):
            self.assertEqual(self.embeddings.embed_query("question"), vector)

    def test_surfaces_provider_404(self) -> None:
        response = Mock(status_code=404)
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(RAGProviderError, "HTTP 404"):
                self.embeddings.embed_query("question")

    def test_rejects_vectors_with_wrong_dimensions(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = [[0.1]]
        response.raise_for_status.return_value = None
        with patch(
            "app.rag.components.requests.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(RAGProviderError, "736"):
                self.embeddings.embed_query("question")

    def test_uses_full_url_or_resolves_legacy_base(self) -> None:
        vector = [0.1] * 736
        response = Mock(status_code=200)
        response.json.return_value = [vector]
        response.raise_for_status.return_value = None
        for settings, expected_url in (
            (
                Settings(
                    _env_file=None,
                    embedding_api_key=SecretStr("test-key"),
                    embedding_api_url="https://provider.test/full/embeddings",
                    embedding_dimensions=736,
                ),
                "https://provider.test/full/embeddings",
            ),
            (
                Settings(
                    _env_file=None,
                    embedding_api_key=SecretStr("test-key"),
                    embedding_base_url="https://provider.test/v3/text/",
                ),
                "https://provider.test/v3/text/embeddings",
            ),
            (
                Settings(
                    _env_file=None,
                    embedding_api_key=SecretStr("test-key"),
                    embedding_base_url="https://provider.test/v2/text/embeddings",
                ),
                "https://provider.test/v2/text/embeddings",
            ),
        ):
            with patch(
                "app.rag.components.requests.post",
                return_value=response,
            ) as post:
                create_embeddings(settings).embed_query("question")
            self.assertEqual(post.call_args.args[0], expected_url)


if __name__ == "__main__":
    unittest.main()
