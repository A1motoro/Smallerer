from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from smallerer.config import Config, Mode, OcrMode, load_toml_config, merge_config_sources


def test_load_nonexistent_toml_returns_empty(tmp_path: Path):
    result = load_toml_config(tmp_path / "nonexistent.toml")
    assert result == {}


def test_load_valid_toml(tmp_path: Path):
    config_file = tmp_path / "test.toml"
    config_file.write_text(
        """
[build]
jobs = 4
max_bytes = 100000000
ocr = "never"
""",
        encoding="utf-8",
    )
    result = load_toml_config(config_file)
    assert result["build"]["jobs"] == 4
    assert result["build"]["max_bytes"] == 100000000
    assert result["build"]["ocr"] == "never"


def test_load_invalid_toml_returns_empty(tmp_path: Path):
    config_file = tmp_path / "invalid.toml"
    config_file.write_text("not valid toml [[[", encoding="utf-8")
    
    with pytest.raises(ValueError) as exc_info:
        load_toml_config(config_file)
    assert "配置文件格式错误" in str(exc_info.value)


def test_merge_config_sources_cli_overrides(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    
    project_config = root / ".smlr.toml"
    project_config.write_text('jobs = 2\nocr = "never"', encoding="utf-8")
    
    cli = {"jobs": 8, "ocr": "auto"}
    merged = merge_config_sources(root, cli)
    
    assert merged["jobs"] == 8
    assert merged["ocr"] == "auto"


def test_merge_config_sources_project_overrides_global(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    
    global_dir = tmp_path / "home" / ".config" / "smlr"
    global_dir.mkdir(parents=True)
    global_config = global_dir / "config.toml"
    global_config.write_text('jobs = 2\nmax_bytes = 1000000', encoding="utf-8")
    
    project_config = root / ".smlr.toml"
    project_config.write_text('jobs = 4', encoding="utf-8")
    
    # Mock home directory
    import os
    old_home = os.environ.get("HOME")
    try:
        os.environ["HOME"] = str(tmp_path / "home")
        merged = merge_config_sources(root, {})
        assert merged["jobs"] == 4
        assert merged["max_bytes"] == 1000000
    finally:
        if old_home:
            os.environ["HOME"] = old_home
        else:
            os.environ.pop("HOME", None)


def test_merge_config_none_values_ignored(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    
    project_config = root / ".smlr.toml"
    project_config.write_text('jobs = 4\nocr = "never"', encoding="utf-8")
    
    cli = {"jobs": None, "max_bytes": 500000}
    merged = merge_config_sources(root, cli)
    
    assert merged["jobs"] == 4
    assert merged["ocr"] == "never"
    assert merged["max_bytes"] == 500000
