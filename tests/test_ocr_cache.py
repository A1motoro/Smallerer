from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from smallerer.ocr.cache import OcrCache
from smallerer.ocr.base import TextBlock


def test_ocr_cache_basic_operations(tmp_path: Path):
    """spec §5.5: 页级 OCR 缓存按 content_hash + page_no + ocr 配置摘要存取。"""
    cache_root = tmp_path / "cache"
    cache = OcrCache(cache_root)

    content_hash = "abc123"
    page = 1
    digest = "test_digest"
    backend = "test-backend"

    blocks = [
        TextBlock(text="Line 1", confidence=0.95, y0=0.1, y1=0.15),
        TextBlock(text="Line 2", confidence=0.92, y0=0.2, y1=0.25),
    ]

    # 第一次获取应该返回 None
    result = cache.get(content_hash, page, digest)
    assert result is None

    # 存入缓存
    cache.put(content_hash, page, digest, backend, blocks)

    # 第二次获取应该命中缓存
    result = cache.get(content_hash, page, digest)
    assert result is not None
    assert len(result) == 2
    assert result[0].text == "Line 1"
    assert result[1].text == "Line 2"


def test_ocr_cache_different_pages_isolated(tmp_path: Path):
    """不同页的缓存应该隔离。"""
    cache_root = tmp_path / "cache"
    cache = OcrCache(cache_root)

    content_hash = "abc123"
    digest = "test_digest"
    backend = "test-backend"

    blocks_page1 = [TextBlock(text="Page 1", confidence=0.9, y0=0.1, y1=0.2)]
    blocks_page2 = [TextBlock(text="Page 2", confidence=0.9, y0=0.1, y1=0.2)]

    cache.put(content_hash, 1, digest, backend, blocks_page1)
    cache.put(content_hash, 2, digest, backend, blocks_page2)

    assert cache.get(content_hash, 1, digest)[0].text == "Page 1"
    assert cache.get(content_hash, 2, digest)[0].text == "Page 2"


def test_ocr_cache_survives_between_runs(tmp_path: Path):
    """spec §9.4: OCR 全部命中缓存（重复运行不重新 OCR）。"""
    cache_root = tmp_path / "cache"

    content_hash = "persistent"
    page = 1
    digest = "same_config"
    backend = "test-backend"
    blocks = [TextBlock(text="Cached content", confidence=0.9, y0=0.1, y1=0.2)]

    # 第一次运行：写入缓存
    cache1 = OcrCache(cache_root)
    cache1.put(content_hash, page, digest, backend, blocks)

    # 模拟第二次运行：新建 OcrCache 实例
    cache2 = OcrCache(cache_root)
    result = cache2.get(content_hash, page, digest)

    assert result is not None
    assert result[0].text == "Cached content"


def test_ocr_idempotent_with_cache(tmp_path: Path):
    """spec §9.4-5: 第二次运行应该命中缓存，不重新处理。"""
    from smallerer.application import build
    from smallerer.config import Config, Mode, OcrMode

    root = tmp_path / "corpus"
    root.mkdir()

    # 使用现成的 image-only PDF fixture
    import shutil
    fixtures = Path(__file__).parent / "fixtures" / "generated"
    shutil.copy(fixtures / "image-only.pdf", root / "scan.pdf")

    # Mock OCR 后端以跟踪调用次数
    mock_backend = Mock()
    mock_backend.name = "mock-ocr"
    mock_backend.recognize.return_value = [
        TextBlock(text="Mocked OCR result", confidence=0.9, y0=0.1, y1=0.2)
    ]

    # 需要 patch 在 ocr.service 模块中的 get_backend
    with patch("smallerer.ocr.service.get_backend", return_value=mock_backend):
        # 第一次运行：应该调用 OCR
        cfg1 = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.AUTO).normalized()
        build(cfg1)
        first_call_count = mock_backend.recognize.call_count
        assert first_call_count > 0

        # 第二次运行：应该命中缓存，不再调用 OCR
        cfg2 = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.AUTO).normalized()
        build(cfg2)
        second_call_count = mock_backend.recognize.call_count

        # 调用次数不应增加
        assert second_call_count == first_call_count


def test_ocr_resume_after_interrupt_simulation(tmp_path: Path):
    """spec §9.5: 模拟中断后重跑，只处理未完成的页。"""
    from smallerer.application import build
    from smallerer.config import Config, Mode, OcrMode

    root = tmp_path / "corpus"
    root.mkdir()

    # 使用现成的 image-only PDF fixture
    import shutil
    fixtures = Path(__file__).parent / "fixtures" / "generated"
    shutil.copy(fixtures / "image-only.pdf", root / "scan.pdf")

    mock_backend = Mock()
    mock_backend.name = "mock-ocr"
    mock_backend.recognize.return_value = [
        TextBlock(text="OCR result", confidence=0.9, y0=0.1, y1=0.2)
    ]

    with patch("smallerer.ocr.service.get_backend", return_value=mock_backend):
        cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.AUTO).normalized()

        # 第一次运行：处理所有页
        build(cfg)
        total_pages_first = mock_backend.recognize.call_count
        assert total_pages_first > 0  # 至少处理了一些页

        # 模拟"中断"：清空输出目录但保留缓存
        text_dir = cfg.out / "text"
        if text_dir.exists():
            shutil.rmtree(text_dir)
        manifest_path = cfg.out / "MANIFEST.json"
        if manifest_path.exists():
            manifest_path.unlink()

        # 第二次运行：应该命中所有缓存
        mock_backend.recognize.reset_mock()
        build(cfg)

        # 不应该有新的 OCR 调用（全部命中缓存）
        assert mock_backend.recognize.call_count == 0
