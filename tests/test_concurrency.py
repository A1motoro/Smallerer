from __future__ import annotations

import shutil
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from smallerer.application import build
from smallerer.config import Config, Mode, OcrMode


def copy_corpus(tmp_path: Path) -> Path:
    from tests.test_application import FIXTURES

    root = tmp_path / "corpus"
    shutil.copytree(FIXTURES, root)
    return root


def test_concurrent_processing_with_multiple_workers(tmp_path: Path):
    """验证并发处理正常工作。"""
    root = copy_corpus(tmp_path)

    # 使用多个 worker
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=4, ocr=OcrMode.NEVER).normalized()
    report = build(cfg)

    # 应该成功处理所有文件
    assert report.written > 0
    assert report.layout.index_path.is_file()


def test_broken_process_pool_fallback_to_serial(tmp_path: Path):
    """spec 注释：BrokenProcessPool 时应该退化到串行处理，不影响正确性。

    某些沙箱/容器禁用 POSIX semaphore，会导致 ProcessPoolExecutor 失败。
    并发是性能优化，不应该让正确性失败。
    """
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=4, ocr=OcrMode.NEVER).normalized()

    # Mock ProcessPoolExecutor.map 抛出 BrokenProcessPool
    with patch("smallerer.application.ProcessPoolExecutor") as mock_executor:
        mock_pool = Mock()
        mock_pool.__enter__ = Mock(return_value=mock_pool)
        mock_pool.__exit__ = Mock(return_value=False)
        mock_pool.map.side_effect = BrokenProcessPool("测试：进程池不可用")
        mock_executor.return_value = mock_pool

        # 应该退化到串行处理并成功完成
        report = build(cfg)

        # 验证有文件被处理
        assert report.written > 0
        assert report.layout.index_path.is_file()
        assert len(report.records) > 0


def test_permission_error_fallback_to_serial(tmp_path: Path):
    """某些环境可能因为权限问题无法创建进程池。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=4, ocr=OcrMode.NEVER).normalized()

    with patch("smallerer.application.ProcessPoolExecutor") as mock_executor:
        mock_pool = Mock()
        mock_pool.__enter__ = Mock(return_value=mock_pool)
        mock_pool.__exit__ = Mock(return_value=False)
        mock_pool.map.side_effect = PermissionError("测试：权限不足")
        mock_executor.return_value = mock_pool

        report = build(cfg)

        assert report.written > 0
        assert len(report.records) > 0


def test_oserror_fallback_to_serial(tmp_path: Path):
    """操作系统错误（如 semaphore 不可用）应该退化到串行。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=4, ocr=OcrMode.NEVER).normalized()

    with patch("smallerer.application.ProcessPoolExecutor") as mock_executor:
        mock_pool = Mock()
        mock_pool.__enter__ = Mock(return_value=mock_pool)
        mock_pool.__exit__ = Mock(return_value=False)
        mock_pool.map.side_effect = OSError("测试：OS 资源不可用")
        mock_executor.return_value = mock_pool

        report = build(cfg)

        assert report.written > 0
        assert len(report.records) > 0


def test_serial_mode_always_works(tmp_path: Path):
    """jobs=1 应该始终使用串行处理，不依赖进程池。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()

    # 即使 ProcessPoolExecutor 不可用，jobs=1 也应该工作
    with patch("smallerer.application.ProcessPoolExecutor", side_effect=RuntimeError("不应该被调用")):
        report = build(cfg)

        assert report.written > 0
        assert len(report.records) > 0
