"""质检（spec §5.7）。阈值全部是确定数值，判据不许出现形容词。"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from .config import (
    GARBLED_MIN_TOKEN_LEN,
    GARBLED_REPLACEMENT_RATIO,
    GARBLED_UNPRINTABLE_RATIO,
    QUALITY_EMPTY_TOTAL_CHARS,
    QUALITY_LOW_MEDIAN_CHARS,
    QUALITY_LOW_TOTAL_CHARS,
)
from .model import Status

_WS_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass
class QualityReport:
    status: Status
    chars: int
    nonspace_chars: int
    median_chars_per_page: int
    reasons: list[str] = field(default_factory=list)


def _nonspace(text: str) -> int:
    return len(_WS_RE.sub("", text))


def garbled_reasons(text: str) -> list[str]:
    total = len(text)
    if total == 0:
        return []
    reasons: list[str] = []

    replacement = text.count("\ufffd")
    if replacement / total > GARBLED_REPLACEMENT_RATIO:
        reasons.append(f"替换字符 U+FFFD 占比 {replacement / total:.1%}，超过 1%")

    weird = sum(1 for ch in text if unicodedata.category(ch) in {"Co", "Cn"})
    if weird / total > GARBLED_UNPRINTABLE_RATIO:
        reasons.append(f"私用区或未分配字符占比 {weird / total:.1%}，超过 5%")

    latin = len(_LATIN_RE.findall(text))
    cjk = len(_CJK_RE.findall(text))
    if latin >= 20 and latin > cjk:
        tokens = [t for t in text.split() if t]
        if tokens:
            avg = statistics.fmean(len(t) for t in tokens)
            if avg < GARBLED_MIN_TOKEN_LEN:
                reasons.append(f"平均 token 长度 {avg:.2f}，低于 1.5，疑似字体映射损坏")
    return reasons


def assess(page_texts: list[str]) -> QualityReport:
    full = "\n".join(page_texts)
    chars = len(full)
    nonspace = _nonspace(full)
    per_page = [_nonspace(t) for t in page_texts] or [0]
    median = int(statistics.median(per_page))

    if nonspace < QUALITY_EMPTY_TOTAL_CHARS:
        return QualityReport(
            status=Status.EMPTY,
            chars=chars,
            nonspace_chars=nonspace,
            median_chars_per_page=median,
            reasons=[f"总非空白字符 {nonspace}，低于 {QUALITY_EMPTY_TOTAL_CHARS}"],
        )

    reasons = garbled_reasons(full)
    if reasons:
        return QualityReport(
            status=Status.GARBLED,
            chars=chars,
            nonspace_chars=nonspace,
            median_chars_per_page=median,
            reasons=reasons,
        )

    low: list[str] = []
    if median < QUALITY_LOW_MEDIAN_CHARS:
        low.append(f"页均非空白字符中位数 {median}，低于 {QUALITY_LOW_MEDIAN_CHARS}")
    if chars < QUALITY_LOW_TOTAL_CHARS:
        low.append(f"总字符数 {chars}，低于 {QUALITY_LOW_TOTAL_CHARS}")
    if low:
        return QualityReport(
            status=Status.LOW,
            chars=chars,
            nonspace_chars=nonspace,
            median_chars_per_page=median,
            reasons=low,
        )

    return QualityReport(
        status=Status.OK, chars=chars, nonspace_chars=nonspace, median_chars_per_page=median
    )
