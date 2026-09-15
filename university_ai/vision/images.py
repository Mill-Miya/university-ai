from __future__ import annotations

from university_ai.llm.models import ImageInput


class ImagePreprocessor:
    """Validation boundary. Qt converts/resizes before it reaches this pure layer."""

    def __init__(self, *, max_bytes: int, max_dimension: int) -> None:
        self._max_bytes = max_bytes
        self._max_dimension = max_dimension

    def prepare(self, image: ImageInput) -> ImageInput:
        image.validate(max_bytes=self._max_bytes)
        if image.width and image.height and max(image.width, image.height) > self._max_dimension:
            raise ValueError("image dimensions exceed configured limit; resize at capture boundary")
        return image
