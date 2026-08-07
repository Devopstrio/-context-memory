"""Embedding generation abstraction with production-grade retry and fallback."""

from abc import ABC, abstractmethod
from hashlib import md5

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


class EmbeddingError(Exception):
    """Custom exception for embedding generation failures."""

    pass


class Embedder(ABC):
    """Abstract base class for embedding generation."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the embedding model name."""
        ...

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Return the embedding model version."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the embedding service is healthy."""
        ...


class DummyEmbedder(Embedder):
    """Deterministic embedding generator for development and testing."""

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions
        self._model_name = "dummy-embedder"
        self._model_version = "1.0.0"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate deterministic embedding based on text hash."""
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")
        hash_bytes = md5(text.encode(), usedforsecurity=False).digest()
        seed = int.from_bytes(hash_bytes[:8], "big")
        vector = []
        for i in range(self._dimensions):
            value = ((seed * (i + 1) * 2654435761) % 2**32) / 2**32
            normalized = (value * 2.0) - 1.0
            vector.append(normalized)
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = []
        for text in texts:
            embedding = await self.embed(text)
            embeddings.append(embedding)
        return embeddings

    async def health_check(self) -> bool:
        """Dummy embedder is always healthy."""
        return True


class OpenAIEmbedder(Embedder):
    """OpenAI embedding API client with retry and rate limiting."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self._model_name = model
        self._dimensions = dimensions
        self._model_version = "3.0"
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, EmbeddingError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
    )
    async def embed(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API."""
        import httpx

        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": text,
                        "model": self._model_name,
                        "dimensions": self._dimensions,
                    },
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "OpenAI rate limit hit",
                        retry_after=retry_after,
                    )
                    raise EmbeddingError(f"Rate limited, retry after {retry_after}s")

                if response.status_code != 200:
                    logger.error(
                        "OpenAI API error",
                        status_code=response.status_code,
                        body=response.text,
                    )
                    raise EmbeddingError(f"OpenAI API error: {response.status_code}")

                data = response.json()
                embedding = data["data"][0]["embedding"]
                return embedding
        except httpx.HTTPError as e:
            logger.error("HTTP error generating embedding", error=str(e))
            raise EmbeddingError(f"HTTP error: {str(e)}") from e
        except (KeyError, IndexError) as e:
            logger.error("Invalid response format from OpenAI", error=str(e))
            raise EmbeddingError(f"Invalid response format: {str(e)}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch of texts."""
        embeddings = []
        batch_size = 20
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = await self._embed_single_batch(batch)
            embeddings.extend(batch_embeddings)
        return embeddings

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, EmbeddingError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
    )
    async def _embed_single_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a single batch."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": texts,
                        "model": self._model_name,
                        "dimensions": self._dimensions,
                    },
                )
                if response.status_code != 200:
                    raise EmbeddingError(f"OpenAI API error: {response.status_code}")
                data = response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings
        except httpx.HTTPError as e:
            raise EmbeddingError(f"HTTP error: {str(e)}") from e
        except (KeyError, IndexError) as e:
            raise EmbeddingError(f"Invalid response format: {str(e)}") from e

    async def health_check(self) -> bool:
        """Check OpenAI API health."""
        try:
            await self.embed("health check")
            return True
        except Exception:
            return False
