"""页级 OCR 缓存（spec §5.5）。缓存删掉只会变慢，不影响正确性。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .base import TextBlock


class OcrCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, content_hash: str, page: int, digest: str) -> Path:
        key = f"{content_hash}\0{page}\0{digest}".encode()
        token = hashlib.blake2b(key, digest_size=20).hexdigest()
        return self.root / token[:2] / f"{token}.json"

    def get(self, content_hash: str, page: int, digest: str) -> list[TextBlock] | None:
        path = self._path(content_hash, page, digest)
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict) or data.get("version") != 1:
            return None
        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            return None
        try:
            return [TextBlock(**block) for block in blocks]
        except (TypeError, ValueError):
            return None

    def put(
        self,
        content_hash: str,
        page: int,
        digest: str,
        backend: str,
        blocks: list[TextBlock],
    ) -> None:
        path = self._path(content_hash, page, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "backend": backend,
            "blocks": [
                {
                    "text": block.text,
                    "confidence": block.confidence,
                    "y0": block.y0,
                    "y1": block.y1,
                }
                for block in blocks
            ],
        }
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".smlr-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

