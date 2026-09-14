from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class EmbeddingError(RuntimeError):
    pass


class EmbeddingEngine(Protocol):
    runtime: str
    model: str
    def availability(self) -> bool: ...
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OllamaEmbeddingEngine:
    """Ollama /api/embed adapter restricted to the local loopback server."""
    runtime = "ollama"

    def __init__(self, model: str = "embeddinggemma:300m-qat-q4_0", endpoint: str = "http://127.0.0.1:11434", timeout_seconds: int = 120) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("embedding endpoint must use local loopback HTTP")
        self.model, self._endpoint, self._timeout = model, endpoint.rstrip("/"), timeout_seconds

    def availability(self) -> bool:
        try:
            return self.model in [item.get("name", "") for item in self._json("/api/tags", None).get("models", [])]
        except (URLError, OSError, ValueError):
            return False

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        requested = [text for text in texts if text.strip()]
        if not requested:
            return []
        try:
            result = self._json("/api/embed", {"model": self.model, "input": requested, "truncate": False, "keep_alive": "5m"})
            embeddings = result.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(requested):
                raise EmbeddingError("Ollama returned invalid embeddings")
            vectors = [[float(value) for value in vector] for vector in embeddings]
            if not all(vector for vector in vectors):
                raise EmbeddingError("Ollama returned an empty embedding")
            return vectors
        except (URLError, OSError, ValueError, KeyError, EmbeddingError) as error:
            raise EmbeddingError("local embedding runtime is unavailable or failed") from error

    def _json(self, path: str, payload: dict | None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self._endpoint + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self._timeout) as response:
            return json.loads(response.read().decode("utf-8"))
