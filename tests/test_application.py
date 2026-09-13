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
    assert len(plan.items) == 8
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

