"""按类型分派 extractor。抽取阶段只做保真提取（spec §5.4）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config import Config
from ..model import Document, ExtractError, Kind

Extractor = Callable[[Path, Config], Document]


def get(kind: Kind) -> Extractor:
    if kind is Kind.PDF:
        from .pdf import extract as pdf_extract

        return pdf_extract
    if kind is Kind.DOCX:
        from .docx import extract as docx_extract

        return docx_extract
    if kind is Kind.PPTX:
        from .pptx import extract as pptx_extract

        return pptx_extract
    if kind is Kind.IMAGE:
        from .image import extract as image_extract

        return image_extract
    raise ExtractError("no_extractor", f"没有 {kind.value} 的 extractor")


__all__ = ["Extractor", "get"]
