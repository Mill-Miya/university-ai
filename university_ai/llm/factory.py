from __future__ import annotations

from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.ollama import OllamaBackend
from university_ai.llm.openvino import OpenVINOBackend


def create_model_backend(config: ModelBackendConfig):
    if config.runtime == "ollama": return OllamaBackend(config)
    if config.runtime == "openvino": return OpenVINOBackend(config)
    raise ValueError(f"unsupported local model runtime: {config.runtime}")
