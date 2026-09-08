from datetime import UTC, datetime
import pytest
from university_ai.llm.models import LlmResponse
from university_ai.llm.service import LlmService, LlmServiceError
from university_ai.llm.ollama import OllamaEngine

class FakeEngine:
    def __init__(self, available=True): self.available=available; self.requests=[]; self.stopped=False
    def availability(self): return self.available
    def model_info(self): return {'local_only': True}
    def generate(self, request):
        self.requests.append(request); return LlmResponse('local reply','test','fake',datetime.now(UTC),0.01)
    def shutdown(self): self.stopped=True

def test_local_llm_service_and_ocr_prompt():
    engine=FakeEngine(); service=LlmService(engine)
    reply=service.ask('質問')
    ocr=service.explain_text('電子回路1 Report Deadline 9/30')
    assert reply.text=='local reply' and 'OCR由来' in (engine.requests[1].system_prompt or '') and ocr.created_at.tzinfo is not None
    service.shutdown(); assert engine.stopped

def test_empty_and_unavailable_engine_are_safe():
    with pytest.raises(LlmServiceError,match='empty'): LlmService(FakeEngine()).ask(' ')
    with pytest.raises(LlmServiceError,match='unavailable'): LlmService(FakeEngine(False)).ask('hello')
    with pytest.raises(LlmServiceError,match='empty'): LlmService(FakeEngine()).explain_text('')

def test_thinking_sanitizer_never_returns_reasoning_to_ui():
    sanitize=OllamaEngine._sanitize_final_content
    assert sanitize('<think>private reasoning</think>最終回答') == '最終回答'
    assert sanitize('normal final answer') == 'normal final answer'
    assert sanitize('<think>unclosed reasoning') == ''
