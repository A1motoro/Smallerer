"""两种输出模式的路径解析（spec §3.1、§3.2）。

管道其余部分不许自己拼路径，一律经过 Layout。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import (
    CACHE_DIR_NAME,
    INDEX_NAME,
    INDEX_SHARD_DIR,
    MANIFEST_NAME,
    TEXT_DIR_NAME,
    WARNINGS_NAME,
    Config,
    Mode,
)


@dataclass(frozen=True)
class Layout:
    root: Path
    mode: Mode
    meta_dir: Path
    text_root: Path

    @classmethod
    def from_config(cls, cfg: Config) -> "Layout":
        if cfg.mode is Mode.MIRROR:
            # out 就是镜像根，清单在它下面，文本在 out/text/
            assert cfg.out is not None
            return cls(root=cfg.root, mode=cfg.mode, meta_dir=cfg.out, text_root=cfg.out / TEXT_DIR_NAME)
        # 原地模式：清单集中在 root/_ai-context/，文本贴在源文件旁边
        assert cfg.out is not None
        return cls(root=cfg.root, mode=cfg.mode, meta_dir=cfg.out, text_root=cfg.root)

    @property
    def index_path(self) -> Path:
        return self.meta_dir / INDEX_NAME

    @property
    def index_shard_dir(self) -> Path:
        return self.meta_dir / INDEX_SHARD_DIR

    @property
    def manifest_path(self) -> Path:
        return self.meta_dir / MANIFEST_NAME

    @property
    def warnings_path(self) -> Path:
        return self.meta_dir / WARNINGS_NAME

    @property
    def cache_dir(self) -> Path:
        return self.meta_dir / CACHE_DIR_NAME

    def text_path(self, rel: PurePosixPath) -> Path:
        """源文件相对路径 → 文本文件绝对路径。命名规则：源文件全名 + '.md'。"""
        parent = self.text_root if str(rel.parent) == "." else self.text_root / str(rel.parent)
        return parent / (rel.name + ".md")

    def source_path(self, rel: PurePosixPath) -> Path:
        return self.root / str(rel)

    def rel_to_meta(self, path: Path) -> str:
        """记进 MANIFEST 的路径一律相对于清单目录，整棵树搬走后仍然有效。"""
        return PurePosixPath(os.path.relpath(path, self.meta_dir)).as_posix()

    def from_meta_rel(self, rel: str) -> Path:
        return (self.meta_dir / rel).resolve()

    def excluded_dirs(self) -> list[Path]:
        """遍历时必须整棵剪掉的目录。镜像模式下 meta_dir 就是镜像根，text/ 与 .cache/ 都在其内。"""
        return [self.meta_dir]
