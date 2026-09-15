from __future__ import annotations

from PySide6.QtCore import QBuffer, QIODevice

from university_ai.llm.models import ImageInput


class QtImageEncoder:
    """Qt boundary that converts a captured pixmap into an in-memory PNG payload."""

    def to_image_input(self, image: object) -> ImageInput:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        try:
            if not image.save(buffer, "PNG"):
                raise ValueError("capture image could not be encoded as PNG")
            encoded = bytes(buffer.data())
        finally:
            buffer.close()
        qimage = image.toImage()
        return ImageInput(encoded, "image/png", qimage.width(), qimage.height())
