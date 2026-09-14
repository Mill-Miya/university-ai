from __future__ import annotations

from datetime import UTC, datetime

import pytest

from university_ai.agent.context_builder import ContextBuilder
from university_ai.agent.model_router import ModelRouter
from university_ai.agent.models import AgentRequest
from university_ai.agent.orchestrator import AgentOrchestrator
from university_ai.agent.policy import PolicyEngine
from university_ai.agent.router import IntentRouter
from university_ai.agent.tools.registry import ToolRegistry
from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.factory import create_model_backend
from university_ai.llm.models import LlmRequest, LlmResponse
from university_ai.llm.ollama import OllamaBackend, OllamaEngine
from university_ai.llm.openvino import OpenVINOBackend
from university_ai.llm.service import LlmService, LlmServiceError


class FakeBackend:
    def __init__(self, available=True): self.available, self.requests, self.stopped = available, [], False
    def availability(self): return self.available
    def model_info(self): return {"runtime": "fake", "model": "fake-local"}
    def generate(self, request):
        self.requests.append(request)
        return LlmResponse("backend reply", "fake-local", "fake", datetime.now(UTC), .01)
    def shutdown(self): self.stopped = True


def test_backend_configuration_defaults_and_model_override():
    default = ModelBackendConfig()
    assert default.runtime == "ollama" and default.model == "qwen2.5:3b"
    overridden = ModelBackendConfig(model="test-model", endpoint="http://127.0.0.1:19000", timeout_seconds=9, keep_alive="1m")
    backend = OllamaBackend(overridden)
    assert backend.model_info() == {"runtime": "ollama", "model": "test-model", "endpoint": "http://127.0.0.1:19000", "local_only": True}
    with pytest.raises(ValueError, match="loopback"):
        OllamaBackend(ModelBackendConfig(endpoint="https://example.test"))


def test_ollama_backend_availability_and_generate_without_daemon(monkeypatch):
    backend = OllamaBackend(ModelBackendConfig(model="qwen2.5:3b", keep_alive="1m"))
    captured = {}
    def fake_json(path, payload):
        if path == "/api/tags": return {"models": [{"name": "qwen2.5:3b"}]}
        captured["payload"] = payload
        return {"message": {"content": "final", "thinking": "private"}, "done_reason": "stop", "eval_duration": 2_000_000_000, "eval_count": 10}
    monkeypatch.setattr(backend, "_json", fake_json)
    assert backend.availability()
    result = backend.generate(LlmRequest("hello", max_tokens=384))
    assert result.text == "final" and result.metadata["thinking_present"] is True
    assert captured["payload"]["model"] == "qwen2.5:3b" and captured["payload"]["keep_alive"] == "1m"


def test_backend_factory_and_openvino_skeleton():
    assert isinstance(create_model_backend(ModelBackendConfig()), OllamaBackend)
    openvino = create_model_backend(ModelBackendConfig(runtime="openvino", model="future-model"))
    assert isinstance(openvino, OpenVINOBackend) and not openvino.availability()
    with pytest.raises(RuntimeError, match="not available"):
        openvino.generate(LlmRequest("hello"))
    with pytest.raises(ValueError, match="unsupported"):
        create_model_backend(ModelBackendConfig(runtime="unknown"))


def test_ollama_engine_compatibility_alias_and_llm_service_injection():
    assert OllamaEngine is OllamaBackend
    backend = FakeBackend()
    service = LlmService(backend, ModelBackendConfig(model="configured", temperature=.2, max_tokens=400))
    assert service.ask("質問").text == "backend reply"
    assert backend.requests[0].max_tokens == 400 and backend.requests[0].temperature == .2
    assert service.explain_text("OCR").text == "backend reply"
    assert service.summarize_text("本文").text == "backend reply"
    service.shutdown(); assert backend.stopped
    with pytest.raises(LlmServiceError, match="unavailable"):
        LlmService(FakeBackend(False)).ask("質問")


def test_agent_llm_fallback_stays_backend_agnostic():
    class Context:
        def build(self, now): return {"now": now}
    backend = FakeBackend()
    agent = AgentOrchestrator(IntentRouter(), ContextBuilder(Context()), PolicyEngine(), ModelRouter(), ToolRegistry(PolicyEngine()),
                              llm_service=LlmService(backend))
    result = agent.handle(AgentRequest("こんにちは", datetime.now(UTC)))
    assert result.text == "backend reply" and backend.requests
