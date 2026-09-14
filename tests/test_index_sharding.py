from __future__ import annotations

from pathlib import Path

import pytest

from smallerer.application import build
from smallerer.config import Config, Mode, OcrMode, INDEX_SHARD_THRESHOLD
from smallerer.writers.index import write_index
from smallerer.manifest import Record


def test_index_sharding_above_threshold(tmp_path: Path):
    """spec §3.4: 超过 500 份文件时自动分片，主文件只保留统计与导航。"""
    root = tmp_path / "corpus"
    root.mkdir()

    # 创建超过阈值的文件
    num_files = INDEX_SHARD_THRESHOLD + 50
    subdirs = ["dir_a", "dir_b", "dir_c"]

    for i in range(num_files):
        subdir = subdirs[i % len(subdirs)]
        dir_path = root / subdir
        dir_path.mkdir(exist_ok=True)
        file_path = dir_path / f"file_{i:04d}.txt"
        file_path.write_text(f"Content {i}", encoding="utf-8")

    # 构建
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)

    # 检查主 INDEX.md
    index_path = cfg.out / "INDEX.md"
    assert index_path.is_file()
    index_content = index_path.read_text("utf-8")

    # 应该包含分片说明
    assert "分片" in index_content
    assert "index/" in index_content
    assert INDEX_SHARD_THRESHOLD in [500]  # 验证阈值是 500

    # 应该有导航表
    assert "子目录" in index_content
    assert "dir_a" in index_content
    assert "dir_b" in index_content
    assert "dir_c" in index_content

    # 不应该包含详细的文件列表（已被分片）
    assert "file_0000.txt" not in index_content

    # 检查分片文件
    shard_dir = cfg.out / "index"
    assert shard_dir.is_dir()

    # 应该有三个分片文件对应三个子目录
    shard_a = shard_dir / "dir_a.md"
    shard_b = shard_dir / "dir_b.md"
    shard_c = shard_dir / "dir_c.md"

    assert shard_a.is_file()
    assert shard_b.is_file()
    assert shard_c.is_file()

    # 分片应该包含详细的文件列表
    shard_a_content = shard_a.read_text("utf-8")
    assert "file_" in shard_a_content
    assert "dir_a" in shard_a_content


def test_index_no_sharding_below_threshold(tmp_path: Path):
    """spec §3.4: 文件数不超过 500 时不分片，所有内容在主 INDEX.md。"""
    root = tmp_path / "corpus"
    root.mkdir()

    # 创建远少于阈值的文件
    for i in range(10):
        file_path = root / f"file_{i}.txt"
        file_path.write_text(f"Content {i}", encoding="utf-8")

    # 构建
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)

    # 检查主 INDEX.md
    index_path = cfg.out / "INDEX.md"
    assert index_path.is_file()
    index_content = index_path.read_text("utf-8")

    # 不应该有分片说明
    assert "分片" not in index_content

    # 应该包含所有文件的详细列表
    for i in range(10):
        assert f"file_{i}.txt" in index_content

    # 不应该创建 index/ 分片目录
    shard_dir = cfg.out / "index"
    assert not shard_dir.exists()


def test_index_source_paths_as_plain_text(tmp_path: Path):
    """Section 9.9 acceptance: source file paths should be plain text (not clickable links)
    so INDEX remains usable when .ai-context mirror is copied standalone without corpus."""
    root = tmp_path / "corpus"
    root.mkdir()
    
    # Create test files
    test_file = root / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4\nfake pdf")
    
    subdir = root / "sub"
    subdir.mkdir()
    nested_file = subdir / "nested.txt"
    nested_file.write_text("content", encoding="utf-8")
    
    # Build
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)
    
    # Check INDEX.md
    index_path = cfg.out / "INDEX.md"
    assert index_path.is_file()
    index_content = index_path.read_text("utf-8")
    
    # Source paths should be code-formatted plain text, not markdown links
    # Should contain: `test.pdf` and `sub/nested.txt`
    assert "`test.pdf`" in index_content
    assert "`sub/nested.txt`" in index_content
    
    # Should NOT contain clickable links to source files like [test.pdf](../corpus/test.pdf)
    # (the ../corpus/ path would break when .ai-context is copied alone)
    assert "](../corpus/" not in index_content
    assert "[test.pdf](" not in index_content
    
    # Text sidecar links should still work (they're inside the mirror)
    assert "[文本]" in index_content or "文本" in index_content
