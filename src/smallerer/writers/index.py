"""INDEX.md 与 WARNINGS.md（spec §3.4、§5.7）。

INDEX 是「把这个文件夹丢给 AI」时的默认入口，所以它自己必须永远塞得进 context：
超过 500 份文件就分片，主文件只留统计与导航。
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from ..config import INDEX_SHARD_THRESHOLD, Mode
from ..manifest import Record, write_atomic
from ..model import Status
from ..paths import Layout

_ADVICE = {
    Status.OK.value: "纳入",
    Status.LOW.value: "不建议",
    Status.EMPTY.value: "不建议",
    Status.GARBLED.value: "不建议",
    Status.FAILED.value: "不可用",
    Status.SKIPPED.value: "未处理",
    Status.REGISTERED.value: "纳入（原文即文本）",
}


def _link(label: str, target: Path, base: Path) -> str:
    rel = os.path.relpath(target, base)
    return f"[{label}]({quote(PurePosixPath(rel).as_posix())})"


def _row(record: Record, layout: Layout, base: Path) -> str:
    # Show source path as plain text (not clickable) so INDEX works standalone
    # when the .ai-context mirror is copied without the corpus
    source_cell = f"`{record.rel}`"
    if record.text_rel:
        text_cell = _link("文本", layout.from_meta_rel(record.text_rel), base)
    else:
        text_cell = "—"
    note_bits: list[str] = []
    if record.skip_reason:
        note_bits.append(record.skip_reason)
    if record.error:
        note_bits.append(record.error)
    if record.ocr and record.ocr.get("pages"):
        note_bits.append(f"OCR {len(record.ocr['pages'])} 页")
    if record.has_math:
        note_bits.append("含公式，文本可能失真")
    if record.has_tables:
        note_bits.append("含表格")
    if record.partial:
        note_bits.append("部分抽取")
    note = "；".join(note_bits) if note_bits else ""
    pages = str(record.pages) if record.pages else "—"
    advice = _ADVICE.get(record.status, record.status)
    return f"| {source_cell} | {text_cell} | {record.kind} | {pages} | {record.status} | {advice} | {note} |"


_HEADER = (
    "| 源文件 | 文本 | 类型 | 页数 | 质量 | 建议 | 备注 |\n"
    "|---|---|---|---|---|---|---|"
)


def _summary_lines(records: list[Record]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record.status] += 1
    order = [s.value for s in Status if s.value in counts]
    bits = [f"{status} {counts[status]}" for status in order]
    return [f"共 {len(records)} 份文件：" + "、".join(bits) if bits else "共 0 份文件。"]


def write_index(layout: Layout, records: list[Record], mode: Mode) -> list[Path]:
    written: list[Path] = []
    records = sorted(records, key=lambda r: r.rel)
    base = layout.meta_dir

    head = [
        "# 文件夹地图",
        "",
        f"输出模式：`{mode.value}`。源目录：`{layout.root}`。",
        "",
        *_summary_lines(records),
        "",
        "「建议」列为「不建议」「不可用」的条目，原因见 `WARNINGS.md`。",
        "",
    ]

    if len(records) <= INDEX_SHARD_THRESHOLD:
        body = [_HEADER] + [_row(r, layout, base) for r in records]
        write_atomic(layout.index_path, "\n".join(head + body) + "\n")
        return [layout.index_path]

    groups: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        parts = PurePosixPath(record.rel).parts
        groups[parts[0] if len(parts) > 1 else "(根目录)"].append(record)

    nav = ["| 子目录 | 文件数 | 明细 |", "|---|---|---|"]
    for name in sorted(groups):
        shard_name = "root" if name == "(根目录)" else name.replace("/", "_")
        shard = layout.index_shard_dir / f"{shard_name}.md"
        shard_records = groups[name]
        shard_body = [
            f"# {name}",
            "",
            *_summary_lines(shard_records),
            "",
            _HEADER,
            *[_row(r, layout, shard.parent) for r in shard_records],
        ]
        write_atomic(shard, "\n".join(shard_body) + "\n")
        written.append(shard)
        nav.append(f"| `{name}` | {len(shard_records)} | {_link('打开', shard, base)} |")

    note = [
        f"文件数超过 {INDEX_SHARD_THRESHOLD}，明细已分片到 `index/`，以保证本文件本身塞得进 context。",
        "",
    ]
    write_atomic(layout.index_path, "\n".join(head + note + nav) + "\n")
    written.append(layout.index_path)
    return written


_PROBLEM_STATUSES = {
    Status.LOW.value,
    Status.EMPTY.value,
    Status.GARBLED.value,
    Status.FAILED.value,
    Status.SKIPPED.value,
}


def write_warnings(layout: Layout, records: list[Record], preamble: list[str]) -> Path:
    problems = sorted(
        (r for r in records if r.status in _PROBLEM_STATUSES or r.warnings),
        key=lambda r: (r.status, r.rel),
    )
    lines = ["# 警告", ""]
    for note in preamble:
        lines.append(f"- **{note}**")
    if preamble:
        lines.append("")

    if not problems:
        lines.append("没有需要注意的文件。")
        write_atomic(layout.warnings_path, "\n".join(lines) + "\n")
        return layout.warnings_path

    by_status: dict[str, list[Record]] = defaultdict(list)
    for record in problems:
        by_status[record.status].append(record)

    for status in sorted(by_status):
        lines.append(f"## {status}（{len(by_status[status])}）")
        lines.append("")
        for record in by_status[status]:
            reasons = list(record.warnings)
            if record.skip_reason:
                reasons.insert(0, f"跳过原因：{record.skip_reason}")
            if record.error:
                reasons.insert(0, record.error)
            lines.append(f"- `{record.rel}`")
            for reason in reasons or ["（无附加说明）"]:
                lines.append(f"  - {reason}")
        lines.append("")

    write_atomic(layout.warnings_path, "\n".join(lines) + "\n")
    return layout.warnings_path
