"""MANIFEST.json: idempotency, state, artifact tracking (spec §3.5, §5.3, §5.8).

Key responsibilities:
1. Idempotency: store content_hash + pipeline_version + config_digest per file
2. Artifact tracking: list every generated file for orphan detection (spec §3.5)
3. Mode change detection: warn if switching mirror ↔ in-place
4. Incremental updates: append batch after each write, atomic replace at end

Fast-path check: size + mtime_ns unchanged → skip hash (spec §5.3).
Manifest persists between runs for resume and orphan cleanup.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import PIPELINE_VERSION, SCHEMA_VERSION


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Record:
    rel: str
    kind: str
    status: str
    bytes: int = 0
    mtime_ns: int = 0
    content_hash: str = ""
    text_rel: str | None = None
    extractor: str | None = None
    skip_reason: str | None = None
    error: str | None = None
    pages: int = 0
    chars: int = 0
    chars_per_page_median: int = 0
    text_layer: str = "n/a"
    quality: str | None = None
    has_math: bool = False
    has_tables: bool = False
    partial: bool = False
    ocr: dict | None = None
    removed_running_heads: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0
    pipeline_version: str = PIPELINE_VERSION
    config_digest: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Manifest:
    root: str = ""
    mode: str = ""
    out: str = ""
    config_digest: str = ""
    generated_at: str = ""
    files: dict[str, dict] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    pipeline_version: str = PIPELINE_VERSION
    loaded: bool = False

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            root=data.get("root", ""),
            mode=data.get("mode", ""),
            out=data.get("out", ""),
            config_digest=data.get("config_digest", ""),
            generated_at=data.get("generated_at", ""),
            files=data.get("files", {}) or {},
            artifacts=data.get("artifacts", []) or [],
            summary=data.get("summary", {}) or {},
            schema_version=data.get("schema_version", 0),
            pipeline_version=data.get("pipeline_version", ""),
            loaded=True,
        )

    def record(self, rel: str) -> dict | None:
        return self.files.get(rel)

    def save(self, path: Path) -> None:
        self.generated_at = now_iso()
        self.schema_version = SCHEMA_VERSION
        self.pipeline_version = PIPELINE_VERSION
        payload = {
            "schema_version": self.schema_version,
            "pipeline_version": self.pipeline_version,
            "generated_at": self.generated_at,
            "root": self.root,
            "mode": self.mode,
            "out": self.out,
            "config_digest": self.config_digest,
            "summary": self.summary,
            "artifacts": sorted(self.artifacts),
            "files": self.files,
        }
        write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_atomic(path: Path, text: str) -> None:
    """先写同分区临时文件再原子替换（spec §5.8）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".smlr-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
