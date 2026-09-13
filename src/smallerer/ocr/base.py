"""OCR 后端接口。换实现不许改管道（spec §6.3）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TextBlock:
    text: str
    confidence: float = 0.0
    # 归一化坐标，原点在左上，取值 0–1；页眉页脚判断要用
    y0: float | None = None
    y1: float | None = None


@runtime_checkable
class OcrBackend(Protocol):
    name: str

    def recognize(self, image_bytes: bytes) -> list[TextBlock]:
        """输入一张图的字节，返回按阅读顺序排好的文本块。"""
        ...
