from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from university_ai.llm.models import LlmRequest, LlmResponse


class ModelBackend(Protocol):
    """Required local model runtime boundary used by LlmService and never by Agent/UI."""
    def availability(self) -> bool: ...
    def generate(self, request: LlmRequest) -> LlmResponse: ...
    def model_info(self) -> dict[str, object]: ...
    def shutdown(self) -> None: ...


class MultimodalModelBackend(ModelBackend, Protocol):
    """Future-only extension; Phase 2 does not call this method."""
    def generate_multimodal(self, request: LlmRequest, images: Sequence[bytes]) -> LlmResponse: ...


class ManagedModelBackend(ModelBackend, Protocol):
    """Future-only load lifecycle extension for OpenVINO/llama.cpp runtimes."""
    def load_model(self, model: str) -> None: ...
    def unload_model(self, model: str | None = None) -> None: ...
