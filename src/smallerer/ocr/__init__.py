"""OCR 后端注册（spec §6.3）。

第一版只实现 Apple Vision。非 macOS 上没有可用后端，行为必须明确：`--ocr auto`
降级为不做识别并告警，`--ocr only` 直接失败。跨平台后端是这个接口的第二个实现。
"""

from __future__ import annotations

import sys

from .base import OcrBackend, TextBlock

_cached: OcrBackend | None | str = "unset"


def get_backend() -> OcrBackend | None:
    global _cached
    if _cached != "unset":
        return _cached  # type: ignore[return-value]
    _cached = _load()
    return _cached  # type: ignore[return-value]


def _load() -> OcrBackend | None:
    if sys.platform != "darwin":
        return None
    try:
        from .apple_vision import AppleVisionBackend
    except Exception:
        return None
    try:
        return AppleVisionBackend()
    except Exception:
        return None


def unavailable_reason() -> str:
    if sys.platform != "darwin":
        return "当前平台没有可用的 OCR 后端（第一版只实现 Apple Vision，仅 macOS）"
    return "Apple Vision 不可用，请确认已安装 pyobjc-framework-Vision（pip install 'smallerer[ocr]'）"


__all__ = ["OcrBackend", "TextBlock", "get_backend", "unavailable_reason"]
