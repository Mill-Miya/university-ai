from __future__ import annotations

from typing import Protocol

from university_ai.llm.models import ImageInput, LlmRequest, LlmResponse


class MultimodalBackendError(RuntimeError):
    """Base failure for a backend's optional multimodal capability."""


class MultimodalUnsupportedError(MultimodalBackendError):
    pass


class MultimodalUnavailableError(MultimodalBackendError):
    pass


class ModelBackend(Protocol):
    """Required local model runtime boundary used by LlmService and never by Agent/UI."""
    def availability(self) -> bool: ...
    def generate(self, request: LlmRequest) -> LlmResponse: ...
    def model_info(self) -> dict[str, object]: ...
    def shutdown(self) -> None: ...


class MultimodalModelBackend(ModelBackend, Protocol):
    """Optional image capability; image data remains in memory at this boundary."""
    def generate_multimodal(self, request: LlmRequest, images: tuple[ImageInput, ...]) -> LlmResponse: ...


class ManagedModelBackend(ModelBackend, Protocol):
    """Future-only load lifecycle extension for OpenVINO/llama.cpp runtimes."""
    def load_model(self, model: str) -> None: ...
    def unload_model(self, model: str | None = None) -> None: ...
