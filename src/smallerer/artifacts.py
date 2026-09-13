"""生成物身份判定（spec §3.5 第 1、2 条）。

一旦允许原地生成，「哪些文件是我们造的」就必须有可靠答案，否则第二轮会把自己的
产物当输入。第一判据是 MANIFEST 登记；这里实现的是 MANIFEST 丢失时的前置块兜底。
"""

from __future__ import annotations

from pathlib import Path

_PROBE_BYTES = 4096


def looks_like_artifact_name(path: Path) -> bool:
    """命名规则是源文件全名 + '.md'，所以生成物一定是双后缀。"""
    return path.suffix.lower() == ".md" and Path(path.stem).suffix != ""


def has_pipeline_front_matter(path: Path) -> bool:
    """开头的 YAML 前置块里有 pipeline_version 就认作本工具生成物。"""
    try:
        with path.open("rb") as fh:
            head = fh.read(_PROBE_BYTES)
    except OSError:
        return False
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text.startswith("---"):
        return False
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        if line.startswith("pipeline_version:"):
            return True
    # 前置块比探测长度还长的情况不该发生，保守判否
    return False


def is_generated(path: Path) -> bool:
    return looks_like_artifact_name(path) and has_pipeline_front_matter(path)
