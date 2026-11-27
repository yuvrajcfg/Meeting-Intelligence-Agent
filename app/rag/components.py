import math

import chromadb
from chromadb.api import ClientAPI
from langchain_chroma import Chroma
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import LLM
from pydantic import SecretStr
import requests

from app.config import Settings


class RAGConfigurationError(RuntimeError):
    pass


class RAGProviderError(RuntimeError):
    pass


class RAGDependencyError(RuntimeError):
    pass


class CustomLLM(LLM):
    model: str
    endpoint_url: str
    api_key: SecretStr
    temperature: float = 0.0
    top_p: float = 0.9
    max_tokens: int = 1000

    @property
    def _llm_type(self) -> str:
        return "custom-llm"

    def _call(
        self,
        prompt: str,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> str:
        del run_manager
        if kwargs:
            raise RAGProviderError(
                "The LLM provider adapter does not support per-request options."
            )
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if stop:
            payload["stop"] = stop

        try:
            response = requests.post(
                self.endpoint_url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": self.api_key.get_secret_value(),
                },
                json=payload,
                timeout=(5, 60),
            )
        except requests.RequestException as error:
            raise RAGProviderError(
                "Could not reach the LLM provider. Check LLM_BASE_URL and network access."
            ) from error

        if response.status_code == 404:
            raise RAGProviderError(
                "The LLM provider returned HTTP 404. Check that LLM_BASE_URL is the "
                "complete endpoint URL supported by your account."
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RAGProviderError(
                f"The LLM provider rejected the request "
                f"(HTTP {response.status_code}). Check its API key and request format."
            ) from error

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise RAGProviderError("The LLM provider returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise RAGProviderError("The LLM provider response must be a JSON object.")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RAGProviderError(
                "The LLM provider response must contain a first choice."
            )
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RAGProviderError(
                "The LLM provider response must contain message content."
            )
        return message["content"]


class CustomEmbeddings(Embeddings):
    def __init__(
        self,
        *,
        api_key: str,
        endpoint_url: str,
        dimensions: int,
    ) -> None:
        self._headers = {
            "Content-Type": "application/json",
            "X-API-KEY": api_key,
        }
        self._endpoint_url = endpoint_url
        self._dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            try:
                response = requests.post(
                    self._endpoint_url,
                    headers=self._headers,
                    json={"texts": [text], "dimensions": self._dimensions},
                    timeout=(5, 60),
                )
            except requests.RequestException as error:
                raise RAGProviderError(
                    "Could not reach the embedding provider. Check "
                    "EMBEDDING_API_URL and network access."
                ) from error

            if response.status_code == 404:
                raise RAGProviderError(
                    "The embedding provider returned HTTP 404. Check that "
                    "EMBEDDING_API_URL matches the provider's documented endpoint."
                )
            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                raise RAGProviderError(
                    f"The embedding provider rejected the request "
                    f"(HTTP {response.status_code}). Check its API key and request format."
                ) from error

            try:
                batch_vectors = response.json()
            except requests.exceptions.JSONDecodeError as error:
                raise RAGProviderError(
                    "The embedding provider returned invalid JSON."
                ) from error
            vectors.extend(self._validate_vectors(batch_vectors, 1))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def _validate_vectors(
        self,
        value: object,
        expected_count: int,
    ) -> list[list[float]]:
        if isinstance(value, dict):
            value = value.get("embeddings")
        if (
            expected_count == 1
            and isinstance(value, list)
            and len(value) == self._dimensions
            and all(
                not isinstance(item, bool)
                and isinstance(item, (int, float))
                and math.isfinite(item)
                for item in value
            )
        ):
            value = [value]
        if not isinstance(value, list) or len(value) != expected_count:
            raise RAGProviderError(
                "The embedding provider response must contain one vector per text."
            )

        vectors: list[list[float]] = []
        for vector in value:
            if (
                not isinstance(vector, list)
                or len(vector) != self._dimensions
                or any(
                    isinstance(item, bool)
                    or not isinstance(item, (int, float))
                    or not math.isfinite(item)
                    for item in vector
                )
            ):
                raise RAGProviderError(
                    "The embedding provider returned an invalid vector; expected "
                    f"{self._dimensions} finite numeric values."
                )
            vectors.append([float(item) for item in vector])
        return vectors


def create_chroma_client(settings: Settings) -> ClientAPI:
    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
    )


def _secret_value(value: SecretStr | None) -> str:
    return value.get_secret_value() if value is not None else ""


def _chat_configuration(settings: Settings) -> tuple[str, str, str]:
    api_key = _secret_value(settings.llm_api_key)
    endpoint_url = settings.llm_base_url or ""
    model = settings.llm_model
    if not api_key or not endpoint_url or not model:
        raise RAGConfigurationError(
            "Set LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL in .env."
        )
    return api_key, endpoint_url, model


def _embedding_configuration(settings: Settings) -> tuple[str, str]:
    api_key = _secret_value(settings.embedding_api_key)
    endpoint_url = settings.embedding_api_url
    if not endpoint_url and settings.embedding_base_url:
        base_url = settings.embedding_base_url.rstrip("/")
        endpoint_url = (
            base_url
            if base_url.endswith("/embeddings")
            else f"{base_url}/embeddings"
        )
    if not api_key or not endpoint_url:
        raise RAGConfigurationError(
            "Set EMBEDDING_API_KEY and EMBEDDING_API_URL in .env."
        )
    return api_key, endpoint_url


def create_embeddings(settings: Settings) -> CustomEmbeddings:
    api_key, endpoint_url = _embedding_configuration(settings)
    return CustomEmbeddings(
        api_key=api_key,
        endpoint_url=endpoint_url,
        dimensions=settings.embedding_dimensions,
    )


def create_chat_model(settings: Settings) -> CustomLLM:
    api_key, endpoint_url, model = _chat_configuration(settings)
    return CustomLLM(
        model=model,
        api_key=SecretStr(api_key),
        endpoint_url=endpoint_url,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=settings.llm_max_tokens,
    )


def create_vector_store(settings: Settings) -> Chroma:
    return Chroma(
        client=create_chroma_client(settings),
        collection_name="meeting_transcripts",
        embedding_function=create_embeddings(settings),
        collection_metadata={"hnsw:space": "cosine"},
    )
