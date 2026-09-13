"""图片 extractor（spec §6.2）：建立一个待 OCR 的合成页。"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Document, Kind, Page, TextLayer


def extract(path: Path, cfg: Config) -> Document:
    out = Document(kind=Kind.IMAGE, extractor="ocr", page_label="Page")
    out.total_pages = 1
    out.text_layer = TextLayer.NONE
    out.pages = [Page(number=1, lines=[], height=1.0, image_ratio=1.0)]
    out.pages_needing_ocr = [1]
    return out
