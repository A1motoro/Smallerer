"""Text normalization for CJK/Latin mixed-layout documents (spec §5.6).

CJK/Latin mixed line wrapping is the main challenge here. Rules must be:
- Deterministic (same input → same output)
- Testable (covered by test_normalize.py)
- Replaceable as a whole if needed

Steps (spec §5.6 order):
1. Clean: UTF-8, LF, strip unprintable (keep PUA for garbled detection)
2. Merge soft wraps: CJK/Latin-aware line joining
3. No forced spaces between CJK and Latin (that's rewriting, not normalizing)
4. Strip running headers/footers (repeated across pages in top/bottom 8% band)

Removed running heads are recorded in YAML front matter for visibility.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import defaultdict

from .config import (
    RUNNING_HEAD_BAND_RATIO,
    RUNNING_HEAD_MAX_CHARS,
    RUNNING_HEAD_MIN_REPEATS,
    SHORT_LINE_RATIO,
)
from .model import Line, Page

_CJK = (
    r"\u2e80-\u2fdf\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uf900-\ufaff\uff66-\uff9f\U00020000-\U0002ebef"
)
_CJK_RE = re.compile(f"[{_CJK}]")
_CJK_PUNCT = "。！？；：，、）」』】〉》”’"
_SENTENCE_END = set("。！？；：.!?;:…”’)》」』】")
_LATIN_LOWER_RE = re.compile(r"[a-z]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RUN_RE = re.compile(r"\d+")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

_MATH_SYMBOLS = set("∑∫∮√∂∇±≤≥≠≈≡∞αβγδεθλμπρσφψωΓΔΘΛΞΠΣΦΨΩ⊂⊃∪∩∈∉∀∃⇒⇔→←↔")


def clean_text(raw: str) -> str:
    """Step 1: Normalize encoding and strip invisible noise.

    - Unify line endings to LF
    - Remove soft hyphens (U+00AD) and normalize various spaces
    - Strip control chars EXCEPT PUA (Private Use Area)
      Reason: PUA signals garbled CID font mappings (spec §5.7).
              Must keep them visible for quality detection.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    # Keep PUA (Co) for garbled detection; strip other control categories
    return "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf", "Cs"}
    )


def head_key(text: str) -> str:
    """Normalize running head for frequency counting.

    Digits → %d so "Page 3" and "Page 4" count as the same header.
    """
    return _DIGIT_RUN_RE.sub("%d", " ".join(text.split()))


def strip_running_heads(pages: list[Page], keep: bool = False) -> list[str]:
    """Step 4: Remove repeated headers/footers, return list of removed text.

    Logic:
    - With coords: lines in top/bottom 8% band, repeated >= 3 pages
    - No coords (OCR): pure frequency, repeated >= max(3, 50% of pages)

    Removed content is returned for YAML front matter (visibility requirement).
    """
    if keep or len(pages) < RUNNING_HEAD_MIN_REPEATS:
        return []

    with_coords = [p for p in pages if p.height and any(line.y0 is not None for line in p.lines)]
    use_coords = len(with_coords) == len(pages)
    threshold = (
        RUNNING_HEAD_MIN_REPEATS
        if use_coords
        else max(RUNNING_HEAD_MIN_REPEATS, int(len(pages) * 0.5))
    )

    pages_by_key: dict[str, set[int]] = defaultdict(set)
    for page in pages:
        for line in page.lines:
            body = line.text.strip()
            if not body or len(body) > RUNNING_HEAD_MAX_CHARS:
                continue
            if use_coords and not _in_band(line, page):
                continue
            pages_by_key[head_key(body)].add(page.number)

    doomed = {key for key, seen in pages_by_key.items() if len(seen) >= threshold}
    if not doomed:
        return []

    for page in pages:
        page.lines = [
            line
            for line in page.lines
            if not (
                line.text.strip()
                and head_key(line.text.strip()) in doomed
                and (not use_coords or _in_band(line, page))
            )
        ]
    return sorted(doomed)


def _in_band(line: Line, page: Page) -> bool:
    if line.y0 is None or not page.height:
        return False
    band = page.height * RUNNING_HEAD_BAND_RATIO
    bottom = line.y1 if line.y1 is not None else line.y0
    return line.y0 <= band or bottom >= page.height - band


def merge_soft_wraps(lines: list[str]) -> str:
    """Step 2: Merge soft line wraps. Rule order follows spec §5.6.

    Decision chain (first match wins):
    1. Prev ends with sentence punctuation → keep newline
    2. Prev shorter than 60% of median line length → keep (likely heading/list)
    3. Both ends CJK → join with no space
    4. Prev ends "-" + Latin, cur starts lowercase Latin → dehyphenate and join
    5. Prev ends Latin/comma, cur starts lowercase Latin → join with space
    6. Otherwise → keep newline

    Short_cut = median * 0.6 identifies headings/list items.
    """
    lengths = [len(line.strip()) for line in lines if line.strip()]
    median = statistics.median(lengths) if lengths else 0.0
    short_cut = median * SHORT_LINE_RATIO

    out: list[str] = []
    for raw in lines:
        cur = raw.strip()
        if not cur:
            out.append("")
            continue
        if not out or not out[-1]:
            out.append(cur)
            continue
        prev = out[-1]
        joined = _join(prev, cur, short_cut)
        if joined is None:
            out.append(cur)
        else:
            out[-1] = joined
    return "\n".join(out)


def _join(prev: str, cur: str, short_cut: float) -> str | None:
    """Try to join two lines. Returns merged text or None to keep newline.

    Implements spec §5.6 soft-wrap merging rules (see merge_soft_wraps docstring).
    """
    tail, head = prev[-1], cur[0]

    if tail in _SENTENCE_END:
        return None
    if len(prev) < short_cut:
        return None
    if _CJK_RE.match(tail) or tail in _CJK_PUNCT:
        if _CJK_RE.match(head) or head in _CJK_PUNCT:
            return prev + cur
        return None
    if tail == "-" and len(prev) >= 2 and _LATIN_LETTER_RE.match(prev[-2]):
        if _LATIN_LOWER_RE.match(head):
            return prev[:-1] + cur
        return None
    if (_LATIN_LETTER_RE.match(tail) or tail == ",") and _LATIN_LOWER_RE.match(head):
        return prev + " " + cur
    return None


def collapse_blank_lines(text: str) -> str:
    """第 1 步的后半：连续空行压到最多一个，行尾去空白。"""
    stripped = "\n".join(line.rstrip() for line in text.split("\n"))
    return _BLANK_RUN_RE.sub("\n\n", stripped).strip("\n")


def normalize_page(page: Page) -> str:
    lines = [clean_text(line.text) for line in page.lines]
    flat: list[str] = []
    for chunk in lines:
        flat.extend(chunk.split("\n"))
    return collapse_blank_lines(merge_soft_wraps(flat))


def looks_mathy(text: str) -> bool:
    """公式检测：只用于标记 has_math，不改内容（spec §7）。"""
    if not text:
        return False
    hits = sum(1 for ch in text if ch in _MATH_SYMBOLS)
    if hits >= 8:
        return True
    return hits / max(len(text), 1) > 0.004 and hits >= 3
