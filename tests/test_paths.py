from pathlib import Path, PurePosixPath

from smallerer.config import Config, Mode
from smallerer.paths import Layout


def test_mirror_paths(tmp_path: Path):
    root = tmp_path / "course"
    root.mkdir()
    cfg = Config(root=root, mode=Mode.MIRROR).normalized()
    layout = Layout.from_config(cfg)
    assert layout.meta_dir == tmp_path / "course.ai-context"
    assert layout.text_path(PurePosixPath("lectures/ch01.pdf")) == (
        tmp_path / "course.ai-context/text/lectures/ch01.pdf.md"
    )


def test_in_place_paths(tmp_path: Path):
    root = tmp_path / "course"
    root.mkdir()
    cfg = Config(root=root, mode=Mode.IN_PLACE).normalized()
    layout = Layout.from_config(cfg)
    assert layout.meta_dir == root / "_ai-context"
    assert layout.text_path(PurePosixPath("lectures/ch01.pdf")) == (
        root / "lectures/ch01.pdf.md"
    )

