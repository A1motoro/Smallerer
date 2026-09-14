"""配置与全局常量。所有阈值都来自 spec，改这里就是改 spec。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PIPELINE_VERSION = "0.1.0"
SCHEMA_VERSION = 1

META_DIR_NAME = "_ai-context"
TEXT_DIR_NAME = "text"
CACHE_DIR_NAME = ".cache"
INDEX_NAME = "INDEX.md"
INDEX_SHARD_DIR = "index"
MANIFEST_NAME = "MANIFEST.json"
WARNINGS_NAME = "WARNINGS.md"
IGNORE_FILE_NAME = ".smlrignore"
MIRROR_SUFFIX = ".ai-context"

# spec §5.1
IGNORED_DIR_NAMES = frozenset({"node_modules", "__pycache__", ".venv", ".git", "venv"})
TRIVIAL_IMAGE_MIN_PIXELS = 200 * 200
TRIVIAL_IMAGE_MIN_BYTES = 20 * 1024

# spec §3.4
INDEX_SHARD_THRESHOLD = 500

# spec §5.7
QUALITY_LOW_MEDIAN_CHARS = 100
QUALITY_LOW_TOTAL_CHARS = 200
QUALITY_EMPTY_TOTAL_CHARS = 50
GARBLED_REPLACEMENT_RATIO = 0.01
GARBLED_UNPRINTABLE_RATIO = 0.05
GARBLED_MIN_TOKEN_LEN = 1.5

# spec §5.6
RUNNING_HEAD_MIN_REPEATS = 3
RUNNING_HEAD_BAND_RATIO = 0.08
RUNNING_HEAD_MAX_CHARS = 120
SHORT_LINE_RATIO = 0.6


class Mode(str, Enum):
    MIRROR = "mirror"
    IN_PLACE = "in-place"


class OcrMode(str, Enum):
    AUTO = "auto"
    NEVER = "never"
    ONLY = "only"


def default_jobs() -> int:
    return min(8, os.cpu_count() or 1)


def load_toml_config(path: Path) -> dict:
    """加载 TOML 配置文件，不存在返回空字典，格式错误时抛出异常。

    spec §2: 失败可见。Bad TOML 必须明确报错，不能静默当空配置。
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"配置文件格式错误（{path}）：{exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"无法读取配置文件（{path}）：{exc}") from exc


def merge_config_sources(root: Path, cli_overrides: dict) -> dict:
    """按优先级合并配置：命令行 > <root>/.smlr.toml > ~/.config/smlr/config.toml > 默认。

    spec §4: 配置优先级明确。配置文件全部可选，工具不主动创建。
    """
    result = {}

    # 最低优先级：全局配置
    global_config = Path.home() / ".config" / "smlr" / "config.toml"
    global_data = load_toml_config(global_config)
    # 支持扁平配置或 [build] section
    if "build" in global_data:
        result.update(global_data["build"])
    else:
        result.update(global_data)

    # 中等优先级：项目配置
    project_config = root / ".smlr.toml"
    project_data = load_toml_config(project_config)
    if "build" in project_data:
        result.update(project_data["build"])
    else:
        result.update(project_data)

    # 最高优先级：命令行覆盖
    result.update({k: v for k, v in cli_overrides.items() if v is not None})

    return result


@dataclass(frozen=True)
class Config:
    root: Path
    mode: Mode
    out: Path | None = None
    ocr: OcrMode = OcrMode.AUTO
    jobs: int = 0
    force: bool = False
    prune: bool = False
    dry_run: bool = False
    include_images: bool = True
    keep_running_heads: bool = False
    follow_symlinks: bool = False
    max_bytes: int = 512 * 1024 * 1024
    max_ocr_pages: int = 500
    ocr_page_threshold: int = 30
    ocr_dpi: int = 200

    def normalized(self) -> "Config":
        cfg = self
        if cfg.jobs <= 0:
            cfg = replace(cfg, jobs=default_jobs())
        root = cfg.root.expanduser().resolve()
        out = cfg.out
        if cfg.mode is Mode.MIRROR:
            out = (out.expanduser().resolve() if out else root.parent / f"{root.name}{MIRROR_SUFFIX}")
        else:
            out = root / META_DIR_NAME
        return replace(cfg, root=root, out=out)

    def content_digest(self) -> str:
        """只包含会改变输出内容的选项。模式只影响路径，不进摘要。"""
        payload = {
            "ocr": self.ocr.value,
            "include_images": self.include_images,
            "keep_running_heads": self.keep_running_heads,
            "max_bytes": self.max_bytes,
            "max_ocr_pages": self.max_ocr_pages,
            "ocr_page_threshold": self.ocr_page_threshold,
            "ocr_dpi": self.ocr_dpi,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.blake2b(blob, digest_size=8).hexdigest()
