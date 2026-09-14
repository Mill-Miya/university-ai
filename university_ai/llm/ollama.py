from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.models import LlmRequest, LlmResponse


class OllamaBackend:
    """Localhost-only adapter for an already-running Ollama server."""

    runtime = "ollama"

    def __init__(
        self,
        config: ModelBackendConfig | None = None,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: int | None = None,
        keep_alive: str | None = None,
    ) -> None:
        base = config or ModelBackendConfig()
        if base.runtime != self.runtime:
            raise ValueError("OllamaBackend requires runtime='ollama'")
        self._config = ModelBackendConfig(
            runtime=base.runtime,
            model=model or base.model,
            endpoint=endpoint or base.endpoint,
            timeout_seconds=timeout_seconds or base.timeout_seconds,
            keep_alive=keep_alive or base.keep_alive,
            temperature=base.temperature,
            max_tokens=base.max_tokens,
            think=base.think,
        )
        parsed = urlparse(self._config.endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("OllamaBackend endpoint must use local loopback HTTP")

    def availability(self) -> bool:
        try:
            return any(item.get("name", "").split(":")[0] == self._config.model.split(":")[0]
                       for item in self._json("/api/tags", None).get("models", []))
        except (URLError, OSError, ValueError):
            return False

    def model_info(self) -> dict[str, object]:
        return {"runtime": self.runtime, "model": self._config.model, "endpoint": self._config.endpoint, "local_only": True}

    def generate(self, request: LlmRequest) -> LlmResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": self._user_content(request.prompt)})
        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "think": self._config.think,
            "keep_alive": self._config.keep_alive,
            "options": {"temperature": request.temperature, "num_predict": max(request.max_tokens, 256)},
        }
        started = time.monotonic()
        result = self._json("/api/chat", payload)
        message = result.get("message") or {}
        content = self._sanitize_final_content(str(message.get("content") or ""))
        eval_duration = result.get("eval_duration", 0) or 0
        eval_count = result.get("eval_count", 0) or 0
        return LlmResponse(content, self._config.model, self.runtime, datetime.now(UTC), time.monotonic() - started, {
            "done_reason": result.get("done_reason"),
            "load_duration_ns": result.get("load_duration", 0),
            "prompt_eval_count": result.get("prompt_eval_count", 0),
            "prompt_eval_duration_ns": result.get("prompt_eval_duration", 0),
            "eval_duration_ns": eval_duration,
            "eval_count": eval_count,
            "tokens_per_second": eval_count / (eval_duration / 1e9) if eval_duration else 0,
            "thinking_present": bool(message.get("thinking")),
        })

    def shutdown(self) -> None:
        pass  # Runtime ownership remains with the user-managed local Ollama service.

    def _json(self, path: str, payload: dict | None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self._config.endpoint.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=self._config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _user_content(self, prompt: str) -> str:
        """Use Qwen's soft switch only for models that expose a thinking mode.

        Qwen2.5 is the current non-thinking default.  Prefixing its normal
        prompts with ``/no_think`` can make it answer with that literal token.
        The API-level ``think`` flag remains present for every backend call.
        """
        if self._config.model.lower().startswith("qwen3"):
            return "/no_think\n" + prompt
        return prompt

    @staticmethod
    def _sanitize_final_content(content: str) -> str:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.IGNORECASE | re.DOTALL)
        if "<think>" in content.lower():
            return ""
        return content.strip()


# Existing public import remains valid while production code adopts OllamaBackend.
OllamaEngine = OllamaBackend
