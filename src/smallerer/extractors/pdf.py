"""PDF extractor（spec §6.1）。主战场。"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from ..config import Config
from ..model import Document, ExtractError, Kind, Line, Page, TextLayer

_WS_RE = re.compile(r"\s+")
_SPARSE_CHARS = 200


def _nonspace(text: str) -> int:
    return len(_WS_RE.sub("", text))


def _table_regions(page: "pymupdf.Page") -> tuple[list[tuple[pymupdf.Rect, list[str]]], bool]:
    """返回 (可用的表格区域, 是否检测到表格)。

    PyMuPDF 不给置信度，用「至少 2 行 2 列、空单元不过半」当接受判据；不达标的
    表格保留原始文本行，只置 has_tables 并告警（spec §7）。
    """
    try:
        finder = page.find_tables()
    except Exception:
        return [], False
    accepted: list[tuple[pymupdf.Rect, list[str]]] = []
    detected = False
    for table in getattr(finder, "tables", []):
        detected = True
        try:
            rows = table.extract()
        except Exception:
            continue
        if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
            continue
        cells = [c for row in rows for c in row]
        filled = sum(1 for c in cells if c and str(c).strip())
        if not cells or filled / len(cells) <= 0.5:
            continue
        try:
            markdown = table.to_markdown().strip()
        except Exception:
            continue
        if not markdown:
            continue
        accepted.append((pymupdf.Rect(table.bbox), markdown.split("\n")))
    return accepted, detected


def _page_lines(page: "pymupdf.Page", tables: list[tuple[pymupdf.Rect, list[str]]]) -> list[Line]:
    data = page.get_text("dict")
    items: list[tuple[float, float, Line]] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if not text.strip():
                continue
            x0, y0, x1, y1 = line["bbox"]
            mid = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
            if any(rect.contains(mid) for rect, _ in tables):
                continue
            items.append((y0, x0, Line(text=text, y0=y0, y1=y1)))

    for rect, rows in tables:
        items.append((rect.y0, rect.x0, Line(text="", y0=rect.y0, y1=rect.y0)))
        for offset, row in enumerate(rows):
            items.append((rect.y0, rect.x0 + offset * 1e-6, Line(text=row, y0=rect.y0, y1=rect.y1)))
        items.append((rect.y1, rect.x0, Line(text="", y0=rect.y1, y1=rect.y1)))

    items.sort(key=lambda it: (round(it[0], 1), it[1]))
    return [line for _, _, line in items]


def _image_ratio(page: "pymupdf.Page") -> float:
    area = abs(page.rect.get_area())
    if area <= 0:
        return 0.0
    covered = 0.0
    try:
        infos = page.get_image_info()
    except Exception:
        return 0.0
    for info in infos:
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if not rect.is_empty:
            covered += abs(rect.get_area())
    return min(covered / area, 1.0)


def _classify(page_chars: list[int], threshold: int) -> TextLayer:
    if not page_chars:
        return TextLayer.NONE
    empty = sum(1 for c in page_chars if c < threshold)
    rich = sum(1 for c in page_chars if c >= _SPARSE_CHARS)
    if empty == len(page_chars):
        return TextLayer.NONE
    if empty:
        return TextLayer.MIXED
    if rich == len(page_chars):
        return TextLayer.RICH
    return TextLayer.SPARSE


def extract(path: Path, cfg: Config) -> Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # PyMuPDF 的异常类型随版本变动，统一按损坏处理
        raise ExtractError("corrupt", f"PDF 无法打开：{exc}") from exc

    with doc:
        if doc.needs_pass:
            raise ExtractError("encrypted", "PDF 需要口令，不尝试破解")

        out = Document(
            kind=Kind.PDF,
            extractor=f"pymupdf@{pymupdf.pymupdf_version}",
            page_label="Page",
        )
        out.total_pages = doc.page_count
        page_chars: list[int] = []
        broken = 0

        for index in range(doc.page_count):
            number = index + 1
            try:
                page = doc.load_page(index)
                tables, detected = _table_regions(page)
                lines = _page_lines(page, tables)
                height = page.rect.height
                ratio = _image_ratio(page)
            except Exception as exc:
                broken += 1
                out.warnings.append(f"第 {number} 页读取失败：{exc}")
                out.pages.append(Page(number=number, lines=[], height=None))
                page_chars.append(0)
                continue

            if detected:
                out.has_tables = True
                if not tables:
                    out.warnings.append(f"第 {number} 页检测到表格但结构不可靠，按原始文本输出")

            body = "".join(line.text for line in lines)
            chars = _nonspace(body)
            page_chars.append(chars)
            page_obj = Page(number=number, lines=lines, height=height, image_ratio=ratio)
            out.pages.append(page_obj)

            if chars < cfg.ocr_page_threshold:
                out.pages_needing_ocr.append(number)
            if ratio > 0.6:
                out.image_heavy_pages.append(number)

        out.text_layer = _classify(page_chars, cfg.ocr_page_threshold)
        if broken:
            out.partial = True
            out.warnings.append(f"{broken} 页因结构损坏被跳过")
        return out
