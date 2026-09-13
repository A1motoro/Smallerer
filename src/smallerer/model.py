"""管道内部传递的数据结构。extractor 只负责填这些，不负责排版。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    IMAGE = "image"
    PLAINTEXT = "plaintext"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class Status(str, Enum):
    OK = "ok"
    LOW = "low"
    EMPTY = "empty"
    GARBLED = "garbled"
    FAILED = "failed"
    SKIPPED = "skipped"
    REGISTERED = "registered"
    UNCHANGED = "unchanged"


class TextLayer(str, Enum):
    RICH = "rich"
    SPARSE = "sparse"
    NONE = "none"
    MIXED = "mixed"
    NA = "n/a"


@dataclass
class Line:
    text: str
    y0: float | None = None
    y1: float | None = None


@dataclass
class Page:
    number: int
    lines: list[Line] = field(default_factory=list)
    height: float | None = None
    source: str = "text"  # text | ocr
    image_ratio: float = 0.0

    @property
    def raw_chars(self) -> int:
        return sum(len(line.text.strip()) for line in self.lines)


@dataclass
class Document:
    """extractor 的产物：分页的行，加上抽取过程中发现的事实。"""

    kind: Kind
    extractor: str
    pages: list[Page] = field(default_factory=list)
    page_label: str = "Page"  # Page | Slide | Section
    total_pages: int = 0
    text_layer: TextLayer = TextLayer.NA
    ocr_backend: str | None = None
    ocr_pages: list[int] = field(default_factory=list)
    ocr_chars: int = 0
    pages_needing_ocr: list[int] = field(default_factory=list)
    has_math: bool = False
    has_tables: bool = False
    image_heavy_pages: list[int] = field(default_factory=list)
    partial: bool = False
    warnings: list[str] = field(default_factory=list)


class ExtractError(Exception):
    """抽取失败，且失败原因要写进 MANIFEST 与 WARNINGS。"""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason
