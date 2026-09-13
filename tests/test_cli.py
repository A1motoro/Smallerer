from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from smallerer.cli import main


def test_ocr_only_without_backend_exits_with_code_2(tmp_path: Path):
    """spec §6.3 / §4: --ocr only 在没有后端时必须以退出码 2 失败。"""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "test.txt").write_text("dummy", encoding="utf-8")
    
    with patch("smallerer.ocr.get_backend", return_value=None):
        with patch("smallerer.ocr.unavailable_reason", return_value="测试：OCR 不可用"):
            exit_code = main([
                "build",
                str(root),
                "--mirror",
                "--ocr", "only",
            ])
            
            assert exit_code == 2  # EXIT_USAGE


def test_bad_toml_exits_with_code_2(tmp_path: Path):
    """Bad TOML 必须可见失败，退出码 2。"""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "test.txt").write_text("dummy", encoding="utf-8")
    
    # 创建格式错误的 TOML
    bad_toml = root / ".smlr.toml"
    bad_toml.write_text("not valid [[[", encoding="utf-8")
    
    exit_code = main([
        "build",
        str(root),
        "--mirror",
    ])
    
    assert exit_code == 2  # EXIT_USAGE


def test_toml_config_not_clobbered_by_cli_defaults(tmp_path: Path):
    """e2e: TOML 配置不应该被 CLI argparse 默认值覆盖。
    
    通过真实的 main() 入口，验证项目 .smlr.toml 中设置的值在未显式传递
    CLI 参数时能够生效（不被 argparse 默认值覆盖）。
    """
    root = tmp_path / "corpus"
    root.mkdir()
    
    # 创建一些文件
    (root / "test.txt").write_text("Test content", encoding="utf-8")
    (root / "small.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 100)  # 小图片
    
    # 创建 .smlr.toml 设置非默认值
    toml_config = root / ".smlr.toml"
    toml_config.write_text(
        """
ocr = "never"
max_bytes = 100000000
max_ocr_pages = 100
include_images = false
jobs = 2
""",
        encoding="utf-8",
    )
    
    # 运行 build --dry-run（不传 --ocr, --max-bytes 等参数）
    # 如果 TOML 被正确读取，应该使用 TOML 的值而不是内置默认值
    exit_code = main([
        "build",
        str(root),
        "--mirror",
        "--dry-run",
    ])
    
    assert exit_code == 0
    
    # 验证使用了 TOML 的配置而不是默认值
    # 读取计划输出或使用 Config 直接验证
    from smallerer.config import Config, Mode, OcrMode
    from smallerer.cli import _config_from_build
    import argparse
    
    # 模拟相同的参数解析
    from smallerer.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "build",
        str(root),
        "--mirror",
        "--dry-run",
    ])
    
    cfg = _config_from_build(args)
    
    # 验证 TOML 配置生效
    assert cfg.ocr == OcrMode.NEVER, f"ocr 应该是 TOML 的 'never'，实际是 {cfg.ocr}"
    assert cfg.max_bytes == 100000000, f"max_bytes 应该是 TOML 的 100000000，实际是 {cfg.max_bytes}"
    assert cfg.max_ocr_pages == 100, f"max_ocr_pages 应该是 TOML 的 100，实际是 {cfg.max_ocr_pages}"
    assert cfg.include_images is False, f"include_images 应该是 TOML 的 False，实际是 {cfg.include_images}"
    assert cfg.jobs == 2, f"jobs 应该是 TOML 的 2，实际是 {cfg.jobs}"
