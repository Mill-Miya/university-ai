from __future__ import annotations

from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.models import LlmRequest, LlmResponse


class OpenVINOBackend:
    """Phase 2 availability boundary only; no OpenVINO dependency or model loading yet."""
    runtime = "openvino"
    def __init__(self, config: ModelBackendConfig) -> None:
        if config.runtime != self.runtime:
            raise ValueError("OpenVINOBackend requires runtime='openvino'")
        self._config = config
    def availability(self) -> bool: return False
    def model_info(self) -> dict[str, object]:
        return {"runtime": self.runtime, "model": self._config.model, "available": False, "reason": "not implemented"}
    def generate(self, request: LlmRequest) -> LlmResponse:
        raise RuntimeError("OpenVINO backend is not available in Phase 2")
    def shutdown(self) -> None: pass
    def load_model(self, model: str) -> None: raise RuntimeError("OpenVINO backend is not available in Phase 2")
    def unload_model(self, model: str | None = None) -> None: pass
