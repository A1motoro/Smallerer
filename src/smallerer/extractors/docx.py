"""DOCX extractor（spec §6.2）：正文 + 标题层级。

DOCX 没有稳定页码，所以不造 `## Page N`，而是保留原文标题层级并给每个块一个
`<!-- para:N -->` 锚点。
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..model import Document, ExtractError, Kind, Line, Page, TextLayer

_MAX_HEADING = 6


def _heading_level(style_name: str) -> int | None:
    name = (style_name or "").strip().lower()
    if name.startswith("heading "):
        try:
            return min(int(name.split()[1]), _MAX_HEADING)
        except (ValueError, IndexError):
            return None
    if name in {"title", "标题"}:
        return 1
    if name.startswith("标题"):
        tail = name.replace("标题", "").strip()
        if tail.isdigit():
            return min(int(tail), _MAX_HEADING)
        return 1
    return None


def _table_rows(table) -> list[str]:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([" ".join(cell.text.split()) for cell in row.cells])
    if not rows or max(len(r) for r in rows) < 2:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return out


def extract(path: Path, cfg: Config) -> Document:
    try:
        import docx
    except ImportError as exc:
        raise ExtractError("missing_dependency", f"python-docx 不可用：{exc}") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ExtractError("corrupt", f"DOCX 无法打开：{exc}") from exc

    out = Document(kind=Kind.DOCX, extractor="python-docx", page_label="")
    out.text_layer = TextLayer.NA
    lines: list[Line] = []
    index = 0

    body = document.element.body
    tables = {id(t._element): t for t in document.tables}
    paragraphs = {id(p._element): p for p in document.paragraphs}

    for child in body.iterchildren():
        if id(child) in paragraphs:
            paragraph = paragraphs[id(child)]
            text = " ".join(paragraph.text.split())
            if not text:
                continue
            index += 1
            level = _heading_level(paragraph.style.name if paragraph.style else "")
            lines.append(Line(text=f"<!-- para:{index} -->"))
            if level:
                lines.append(Line(text=f"{'#' * (level + 1)} {text}"))
            else:
                lines.append(Line(text=text))
            lines.append(Line(text=""))
        elif id(child) in tables:
            rows = _table_rows(tables[id(child)])
            if not rows:
                out.has_tables = True
                out.warnings.append("有表格结构不足两列，按原始文本输出")
                continue
            out.has_tables = True
            index += 1
            lines.append(Line(text=f"<!-- para:{index} -->"))
            lines.extend(Line(text=row) for row in rows)
            lines.append(Line(text=""))

    out.pages = [Page(number=1, lines=lines)]
    out.total_pages = 0
    return out
