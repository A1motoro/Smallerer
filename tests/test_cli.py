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
