"""File type identification: extension first, magic bytes verify (spec §5.2).

Strategy:
1. Check extension → guess kind
2. Read head bytes → sniff() actual format
3. Mismatch → trust magic bytes, log warning (e.g. .txt renamed to .pdf)

OOXML (PPTX/DOCX) are ZIP containers, requires content inspection.
Unknown types → skip rather than guess (spec: don't assume plaintext).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .model import Kind

EXT_KIND: dict[str, Kind] = {
    ".pdf": Kind.PDF,
    ".pptx": Kind.PPTX,
    ".docx": Kind.DOCX,
    ".png": Kind.IMAGE,
    ".jpg": Kind.IMAGE,
    ".jpeg": Kind.IMAGE,
    ".webp": Kind.IMAGE,
    ".tif": Kind.IMAGE,
    ".tiff": Kind.IMAGE,
    ".heic": Kind.IMAGE,
    ".heif": Kind.IMAGE,
    ".md": Kind.PLAINTEXT,
    ".markdown": Kind.PLAINTEXT,
    ".txt": Kind.PLAINTEXT,
    ".csv": Kind.PLAINTEXT,
    ".xlsx": Kind.UNSUPPORTED,
    ".xls": Kind.UNSUPPORTED,
    ".html": Kind.UNSUPPORTED,
    ".htm": Kind.UNSUPPORTED,
    ".doc": Kind.UNSUPPORTED,
    ".ppt": Kind.UNSUPPORTED,
}

_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis")


def sniff(head: bytes) -> Kind | None:
    """Sniff file format from magic bytes. Returns None if unrecognized.

    Only confident matches return a Kind; ambiguous → None, defer to extension.
    """
    if head.startswith(b"%PDF-"):
        return Kind.PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Kind.IMAGE
    if head.startswith(b"\xff\xd8\xff"):
        return Kind.IMAGE
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return Kind.IMAGE
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Kind.IMAGE
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Kind.IMAGE
    if head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return Kind.IMAGE
    if head.startswith(b"PK\x03\x04"):
        return Kind.UNKNOWN  # OOXML 家族，需要看容器内容
    return None


def _ooxml_kind(path: Path) -> Kind:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return Kind.UNKNOWN
    if any(n.startswith("word/") for n in names):
        return Kind.DOCX
    if any(n.startswith("ppt/") for n in names):
        return Kind.PPTX
    if any(n.startswith("xl/") for n in names):
        return Kind.UNSUPPORTED
    return Kind.UNKNOWN


def identify(path: Path) -> tuple[Kind, list[str]]:
    warnings: list[str] = []
    ext = path.suffix.lower()
    by_ext = EXT_KIND.get(ext, Kind.UNKNOWN)

    try:
        with path.open("rb") as fh:
            head = fh.read(64)
    except OSError as exc:
        return Kind.UNKNOWN, [f"无法读取文件头：{exc}"]

    if not head:
        return Kind.UNKNOWN, ["空文件"]

    by_magic = sniff(head)
    if by_magic is Kind.UNKNOWN:  # zip 容器，进一步看内容
        by_magic = _ooxml_kind(path)

    if by_magic is None:
        # 没有可识别的 magic：纯文本类信任扩展名，其余按未知处理
        if by_ext is Kind.PLAINTEXT:
            return Kind.PLAINTEXT, warnings
        if by_ext is Kind.UNSUPPORTED:
            return Kind.UNSUPPORTED, warnings
        return Kind.UNKNOWN, warnings

    if by_ext is not Kind.UNKNOWN and by_ext is not by_magic:
        warnings.append(f"扩展名 {ext or '(无)'} 与实际内容不符，按 {by_magic.value} 处理")
    return by_magic, warnings
