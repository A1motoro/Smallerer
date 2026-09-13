from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from smallerer.application import ACTION_COLLISION, build, make_plan, status
from smallerer.config import Config, Mode, OcrMode
from smallerer.manifest import Manifest

FIXTURES = Path(__file__).parent / "fixtures" / "generated"


@pytest.fixture(scope="session", autouse=True)
def generated_fixtures():
    from tests.make_fixtures import main

    main()


def copy_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    shutil.copytree(FIXTURES, root)
    return root


def test_dry_run_does_not_write(tmp_path: Path):
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, dry_run=True, ocr=OcrMode.NEVER).normalized()
    plan = make_plan(cfg)
    assert len(plan.items) == 10  # 包含所有 fixture 文件
    assert not cfg.out.exists()


def test_mirror_build_and_idempotency(tmp_path: Path):
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    first = build(cfg)
    assert first.layout.index_path.is_file()
    assert first.layout.manifest_path.is_file()
    assert (cfg.out / "text/text.pdf.md").is_file()
    assert (cfg.out / "text/notes.txt").read_text("utf-8") == "Already plain text.\n"
    assert root.joinpath("text.pdf").read_bytes().startswith(b"%PDF")

    second_plan = make_plan(cfg)
    actionable = [item for item in second_plan.items if item.action in {"extract", "register"}]
    assert not actionable

    second = build(cfg)
    assert second.written == 0


def test_in_place_second_run_does_not_ingest_artifacts(tmp_path: Path):
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.IN_PLACE, jobs=1, ocr=OcrMode.NEVER).normalized()
    first = build(cfg)
    generated = root / "text.pdf.md"
    assert generated.is_file()
    before = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}

    second = build(cfg)
    after = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert second.written == 0
    assert not root.joinpath("text.pdf.md.md").exists()


def test_existing_user_file_is_never_overwritten(tmp_path: Path):
    root = copy_corpus(tmp_path)
    collision = root / "text.pdf.md"
    collision.write_text("my notes", encoding="utf-8")
    cfg = Config(root=root, mode=Mode.IN_PLACE, jobs=1, ocr=OcrMode.NEVER).normalized()
    plan = make_plan(cfg)
    item = next(item for item in plan.items if item.rel == "text.pdf")
    assert item.action == ACTION_COLLISION
    build(cfg)
    assert collision.read_text("utf-8") == "my notes"


def test_orphan_report_and_prune(tmp_path: Path):
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.IN_PLACE, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)
    root.joinpath("text.pdf").unlink()

    report = status(cfg)
    assert root / "text.pdf.md" in report.orphans

    pruned = build(
        Config(root=root, mode=Mode.IN_PLACE, jobs=1, ocr=OcrMode.NEVER, prune=True).normalized()
    )
    assert root / "text.pdf.md" in pruned.pruned
    assert not root.joinpath("text.pdf.md").exists()


def test_manifest_records_pipeline(tmp_path: Path):
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)
    manifest = Manifest.load(cfg.out / "MANIFEST.json")
    assert manifest.loaded
    assert manifest.mode == "mirror"
    assert "text.pdf" in manifest.files


def test_mixed_pdf_identifies_pages_needing_ocr(tmp_path: Path):
    """spec §5.5, §9.3: 混合 PDF 只 OCR 文字层 < 30 字符的页，其他页用文字层。"""
    root = copy_corpus(tmp_path)
    
    # 使用 mock OCR 后端
    from unittest.mock import Mock
    from smallerer.ocr.base import TextBlock
    
    mock_backend = Mock()
    mock_backend.name = "mock-ocr"
    mock_backend.recognize.return_value = [
        TextBlock(text="Mocked OCR text from scan page", confidence=0.9, y0=0.1, y1=0.2)
    ]
    
    from unittest.mock import patch
    with patch("smallerer.ocr.service.get_backend", return_value=mock_backend):
        cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.AUTO).normalized()
        report = build(cfg)
        
        # 找到 mixed.pdf 的记录
        mixed_record = next((r for r in report.records if r.rel == "mixed.pdf"), None)
        assert mixed_record is not None
        
        # 检查文字层类型应该是 mixed（部分页有文字，部分页需要 OCR）
        assert mixed_record.text_layer == "mixed"
        
        # 验证 OCR 信息
        assert mixed_record.ocr is not None
        assert "pages" in mixed_record.ocr
        ocr_pages = mixed_record.ocr["pages"]
        
        # mixed.pdf 第 2 页是纯图片，应该被 OCR（页号为 2）
        assert 2 in ocr_pages, f"第 2 页（纯图片）应该被 OCR，实际 ocr.pages={ocr_pages}"
        
        # 第 1 和第 3 页有文字层，不应该被 OCR
        assert 1 not in ocr_pages, f"第 1 页有文字层，不应该被 OCR"
        assert 3 not in ocr_pages, f"第 3 页有文字层，不应该被 OCR"
        
        # 检查生成的文本文件
        text_file = cfg.out / "text" / "mixed.pdf.md"
        assert text_file.is_file()
        content = text_file.read_text("utf-8")
        
        # 应该包含三个页标记
        assert "## Page 1" in content
        assert "## Page 2" in content
        assert "## Page 3" in content
        
        # 第 2 页应该标记为 OCR
        assert "<!-- page:2 ocr -->" in content


def test_trivial_image_is_skipped(tmp_path: Path):
    """spec §5.1: 小于 200×200 像素的图片应该被跳过。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    report = build(cfg)
    
    # tiny.png 应该被跳过
    tiny_record = next((r for r in report.records if r.rel == "tiny.png"), None)
    assert tiny_record is not None
    assert tiny_record.status == "skipped"
    assert tiny_record.skip_reason == "trivial_image"
    
    # 不应该生成文本文件
    text_file = cfg.out / "text" / "tiny.png.md"
    assert not text_file.exists()


def test_mirror_mode_copies_plaintext_files(tmp_path: Path):
    """spec §6.2: 镜像模式下纯文本文件复制到 text/，保证整个镜像目录自足。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.MIRROR, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)
    
    # 纯文本文件应该被复制到 text/ 目录
    text_copy = cfg.out / "text" / "notes.txt"
    assert text_copy.is_file()
    assert text_copy.read_text("utf-8") == "Already plain text.\n"
    
    # 原文件不应该被修改
    assert root.joinpath("notes.txt").read_text("utf-8") == "Already plain text.\n"


def test_in_place_mode_does_not_copy_plaintext_files(tmp_path: Path):
    """spec §6.2: 原地模式下纯文本文件只登记，不复制（原文件就在旁边）。"""
    root = copy_corpus(tmp_path)
    cfg = Config(root=root, mode=Mode.IN_PLACE, jobs=1, ocr=OcrMode.NEVER).normalized()
    build(cfg)
    
    # 不应该生成 notes.txt.md
    assert not root.joinpath("notes.txt.md").exists()
    
    # 原文件不应该被修改
    assert root.joinpath("notes.txt").read_text("utf-8") == "Already plain text.\n"
    
    # 但应该在 MANIFEST 中登记
    manifest = Manifest.load(cfg.out / "MANIFEST.json")
    assert "notes.txt" in manifest.files
    assert manifest.files["notes.txt"]["status"] == "registered"

