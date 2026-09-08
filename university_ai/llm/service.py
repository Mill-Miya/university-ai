from __future__ import annotations
from university_ai.llm.models import LlmRequest, LlmResponse

class LlmServiceError(RuntimeError): pass

class LlmService:
    """Application boundary for local model generation; no UI or OCR runtime calls."""
    _OCR_INSTRUCTION = "以下はOCR由来のテキストです。誤認識を含む可能性を考慮して、内容を簡潔に説明してください。"
    def __init__(self, engine) -> None: self._engine = engine
    def ask(self, prompt: str, **options) -> LlmResponse:
        if not prompt or not prompt.strip(): raise LlmServiceError("prompt must not be empty")
        if not self._engine.availability(): raise LlmServiceError("local LLM runtime or model is unavailable")
        response=self._engine.generate(LlmRequest(prompt=prompt.strip(), **options))
        if not response.text.strip(): raise LlmServiceError("local LLM returned no final answer")
        return response
    def explain_text(self, text: str) -> LlmResponse:
        if not text or not text.strip(): raise LlmServiceError("OCR text must not be empty")
        return self.ask(text, system_prompt=self._OCR_INSTRUCTION)
    def summarize_text(self, text: str) -> LlmResponse:
        return self.ask(text, system_prompt="以下のテキストを簡潔に要約してください。")
    def shutdown(self) -> None: self._engine.shutdown()
