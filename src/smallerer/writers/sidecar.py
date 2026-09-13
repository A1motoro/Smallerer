"""单份文本文件的渲染（spec §3.3）。

页锚点 `<!-- page:N -->` 是硬约定，供助手回答「这句出自哪」以及未来切 chunk 使用。
"""

from __future__ import annotations

from pathlib import PurePosixPath

from ..config import PIPELINE_VERSION, SCHEMA_VERSION
from ..manifest import Record, now_iso


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if any(ch in text for ch in ':#{}[]&*!|>%@`"\'\n') or text.strip() != text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _emit(lines: list[str], key: str, value, indent: int = 0) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        lines.append(f"{pad}{key}:")
        for sub_key, sub_value in value.items():
            _emit(lines, sub_key, sub_value, indent + 2)
        return
    if isinstance(value, list):
        if not value:
            lines.append(f"{pad}{key}: []")
            return
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            lines.append(f"{pad}{key}: [" + ", ".join(str(v) for v in value) + "]")
            return
        lines.append(f"{pad}{key}:")
        for item in value:
            lines.append(f"{pad}  - {_scalar(item)}")
        return
    lines.append(f"{pad}{key}: {_scalar(value)}")


def front_matter(record: Record) -> str:
    fields: list[tuple[str, object]] = [
        ("schema_version", SCHEMA_VERSION),
        ("source_rel", record.rel),
        ("bytes", record.bytes),
        ("content_hash", record.content_hash),
        ("kind", record.kind),
        ("pages", record.pages),
        ("extractor", record.extractor or ""),
        ("text_layer", record.text_layer),
    ]
    if record.ocr:
        fields.append(("ocr", record.ocr))
    fields += [
        ("chars", record.chars),
        ("chars_per_page_median", record.chars_per_page_median),
        ("quality", record.quality or record.status),
        ("has_math", record.has_math),
        ("has_tables", record.has_tables),
    ]
    if record.partial:
        fields.append(("partial", True))
    fields += [
        ("removed_running_heads", record.removed_running_heads),
        ("warnings", record.warnings),
        ("generated_at", now_iso()),
        ("pipeline_version", PIPELINE_VERSION),
    ]
    lines: list[str] = ["---"]
    for key, value in fields:
        _emit(lines, key, value)
    lines.append("---")
    return "\n".join(lines)


def render(
    record: Record,
    page_texts: list[tuple[int, str, str]],
    notes: list[str],
    label: str = "Page",
) -> str:
    """page_texts 是 (页号, 来源 text|ocr, 正文) 三元组。"""
    title = PurePosixPath(record.rel).name
    parts = [front_matter(record), "", f"# {title}", ""]

    unit = "页" if label == "Page" else ("张" if label == "Slide" else "节")
    span = f"第 1–{record.pages} {unit}" if record.pages > 1 else "全文"
    parts.append(f"> 本文件由 Smallerer 自动生成，源文件 `{record.rel}` {span}。")
    parts.append("")

    for note in notes:
        parts.append(f"> [!] {note}")
    if notes:
        parts.append("")

    for number, source, body in page_texts:
        text = body.strip()
        if not label:
            # DOCX 这类没有稳定页码的类型：保留原文标题层级，不造合成页标题
            parts.append(text if text else "（无可抽取文字）")
            parts.append("")
            continue
        anchor = f"<!-- page:{number} ocr -->" if source == "ocr" else f"<!-- page:{number} -->"
        parts.append(f"## {label} {number}")
        parts.append(anchor)
        parts.append("")
        parts.append(text if text else "（本页无可抽取文字）")
        parts.append("")

    return "\n".join(parts).rstrip("\n") + "\n"
