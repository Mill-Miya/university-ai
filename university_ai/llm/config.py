from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelBackendConfig:
    """Runtime-neutral local generation configuration with current behavior defaults."""
    runtime: str = "ollama"
    model: str = "qwen2.5:3b"
    endpoint: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 120
    keep_alive: str = "5m"
    temperature: float = 0.3
    max_tokens: int = 512
    think: bool = False

    def __post_init__(self) -> None:
        if not self.runtime or not self.model:
            raise ValueError("runtime and model are required")
        if self.timeout_seconds <= 0 or self.max_tokens <= 0:
            raise ValueError("timeout_seconds and max_tokens must be positive")
