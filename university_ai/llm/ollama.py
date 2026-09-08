from __future__ import annotations
import json, re, time
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import Request, urlopen
from university_ai.llm.models import LlmRequest, LlmResponse

class OllamaEngine:
    """Adapter for an already-running localhost-only Ollama server."""
    runtime = "ollama"
    def __init__(self, model: str = "qwen2.5:3b", endpoint: str = "http://127.0.0.1:11434", timeout_seconds: int = 120) -> None:
        self._model, self._endpoint, self._timeout = model, endpoint.rstrip("/"), timeout_seconds
    def availability(self) -> bool:
        try:
            return any(item.get("name", "").split(":")[0] == self._model.split(":")[0] for item in self._json("/api/tags", None).get("models", []))
        except (URLError, OSError, ValueError): return False
    def model_info(self) -> dict[str, object]: return {"runtime": self.runtime, "model": self._model, "endpoint": self._endpoint, "local_only": True}
    def generate(self, request: LlmRequest) -> LlmResponse:
        messages=[]
        if request.system_prompt: messages.append({"role":"system","content":request.system_prompt})
        messages.append({"role":"user","content":"/no_think\n"+request.prompt})
        payload={"model":self._model,"messages":messages,"stream":False,"think":False,"keep_alive":"5m","options":{"temperature":request.temperature,"num_predict":max(request.max_tokens,256)}}
        started=time.monotonic(); result=self._json("/api/chat",payload); message=result.get("message") or {}
        content=self._sanitize_final_content(str(message.get("content") or ""))
        eval_duration=result.get("eval_duration",0) or 0; eval_count=result.get("eval_count",0) or 0
        return LlmResponse(content,self._model,self.runtime,datetime.now(UTC),time.monotonic()-started,{"done_reason":result.get("done_reason"),"load_duration_ns":result.get("load_duration",0),"prompt_eval_duration_ns":result.get("prompt_eval_duration",0),"eval_count":eval_count,"tokens_per_second":eval_count/(eval_duration/1e9) if eval_duration else 0,"thinking_present":bool(message.get("thinking"))})
    def shutdown(self) -> None: pass # Server ownership stays with the local runtime, never a cloud process.
    def _json(self, path, payload):
        data=None if payload is None else json.dumps(payload).encode("utf-8")
        request=Request(self._endpoint+path,data=data,headers={"Content-Type":"application/json"})
        with urlopen(request,timeout=self._timeout) as response: return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _sanitize_final_content(content: str) -> str:
        content=re.sub(r"<think>.*?</think>", "", content, flags=re.IGNORECASE|re.DOTALL)
        if "<think>" in content.lower(): return ""
        return content.strip()
