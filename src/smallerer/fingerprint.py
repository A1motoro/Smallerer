"""内容指纹（spec §5.3）。

快路径：size 与 mtime_ns 都与上次一致就不算哈希。
正式幂等键：BLAKE2b-256 全文件哈希 + pipeline_version + 配置摘要。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1024 * 1024
_ALGO = "blake2b256"


@dataclass(frozen=True)
class Stat:
    size: int
    mtime_ns: int


def stat_of(path: Path) -> Stat:
    st = path.stat()
    return Stat(size=st.st_size, mtime_ns=st.st_mtime_ns)


def content_hash(path: Path) -> str:
    digest = hashlib.blake2b(digest_size=32)
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return f"{_ALGO}:{digest.hexdigest()}"


def unchanged(stat: Stat, record: dict | None) -> bool:
    """快路径判定：只在 size 与 mtime_ns 都命中时才敢说没变。"""
    if not record:
        return False
    return record.get("bytes") == stat.size and record.get("mtime_ns") == stat.mtime_ns
