"""Directory traversal and ignore rules (spec §5.1).

Default skips (spec):
- Output directories (mirror root, in-place _ai-context/)
- Tool artifacts (generated .md files, manifest, cache)
- Dotfiles/dotdirs (except when explicitly included in .smlrignore)
- Common dev dirs: node_modules, __pycache__, .venv, .git
- Symlinks (unless --follow-symlinks)

.smlrignore: gitignore syntax (via pathspec library).
Does NOT read .gitignore (different semantics).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

import pathspec

from .artifacts import is_generated
from .config import IGNORE_FILE_NAME, IGNORED_DIR_NAMES, Config
from .fingerprint import Stat
from .paths import Layout


@dataclass
class Candidate:
    rel: PurePosixPath
    path: Path
    stat: Stat


def load_ignore_spec(root: Path) -> pathspec.PathSpec | None:
    ignore_file = root / IGNORE_FILE_NAME
    if not ignore_file.is_file():
        return None
    try:
        lines = ignore_file.read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


class Walker:
    def __init__(self, cfg: Config, layout: Layout, known_artifacts: set[Path] | None = None):
        self.cfg = cfg
        self.layout = layout
        self.known_artifacts = known_artifacts or set()
        self.ignore_spec = load_ignore_spec(cfg.root)
        self._excluded = {p.resolve() for p in layout.excluded_dirs()}

    def _dir_excluded(self, path: Path) -> bool:
        name = path.name
        if name.startswith("."):
            return True
        if name in IGNORED_DIR_NAMES:
            return True
        try:
            resolved = path.resolve()
        except OSError:
            return True
        return resolved in self._excluded

    def _ignored_by_spec(self, rel: PurePosixPath, is_dir: bool) -> bool:
        if self.ignore_spec is None:
            return False
        target = f"{rel}/" if is_dir else str(rel)
        return self.ignore_spec.match_file(target)

    def walk(self) -> Iterator[Candidate]:
        root = self.cfg.root
        for dirpath, dirnames, filenames in os.walk(root, followlinks=self.cfg.follow_symlinks):
            here = Path(dirpath)
            kept: list[str] = []
            for name in sorted(dirnames):
                child = here / name
                if not self.cfg.follow_symlinks and child.is_symlink():
                    continue
                if self._dir_excluded(child):
                    continue
                if self._ignored_by_spec(PurePosixPath(child.relative_to(root).as_posix()), is_dir=True):
                    continue
                kept.append(name)
            dirnames[:] = kept

            for name in sorted(filenames):
                path = here / name
                if name.startswith("."):
                    continue
                if not self.cfg.follow_symlinks and path.is_symlink():
                    continue
                rel = PurePosixPath(path.relative_to(root).as_posix())
                if self._ignored_by_spec(rel, is_dir=False):
                    continue
                if self._is_artifact(path):
                    continue
                try:
                    st = path.stat()
                except OSError:
                    continue
                if not path.is_file():
                    continue
                yield Candidate(rel=rel, path=path, stat=Stat(size=st.st_size, mtime_ns=st.st_mtime_ns))

    def _is_artifact(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        if resolved in self.known_artifacts:
            return True
        return is_generated(path)
