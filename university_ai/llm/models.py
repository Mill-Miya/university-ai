from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ImageInput:
    """Backend-neutral in-memory image payload."""

    data: bytes
    mime_type: str = "image/png"
    width: int | None = None
    height: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self, *, max_bytes: int | None = None) -> None:
        if not self.data:
            raise ValueError("image data must not be empty")
        if self.mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError("unsupported image format")
        if (self.width is not None and self.width <= 0) or (self.height is not None and self.height <= 0):
            raise ValueError("image dimensions must be positive")
        if max_bytes is not None and len(self.data) > max_bytes:
            raise ValueError("image input exceeds configured size limit")

@dataclass(frozen=True)
class LlmRequest:
    prompt: str
    system_prompt: str | None = None
    context: str | None = None
    temperature: float = 0.3
    max_tokens: int = 512
    # Perception/evidence data remains separate from the actual user request
    # until the runtime adapter renders the final user message.
    untrusted_data: str | None = None
    messages: tuple[dict[str, str], ...] = ()
    thinking: bool | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    response_schema: dict[str, object] | None = None

@dataclass(frozen=True)
class LlmResponse:
    text: str
    model: str
    runtime: str
    created_at: datetime
    duration_seconds: float
    metadata: dict[str, object] = field(default_factory=dict)
