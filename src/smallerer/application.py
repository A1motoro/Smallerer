"""build / status 的编排（spec §4、§3.5）。"""

from __future__ import annotations

import shutil
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .artifacts import is_generated
from .config import (
    META_DIR_NAME,
    MIRROR_SUFFIX,
    TRIVIAL_IMAGE_MIN_BYTES,
    TRIVIAL_IMAGE_MIN_PIXELS,
    Config,
    Mode,
)
from .fingerprint import content_hash
from .identify import identify
from .manifest import Manifest, Record, write_atomic
from .model import Kind, Status
from .paths import Layout
from .pipeline import FileResult, Job, process
from .walker import Candidate, Walker
from .writers import write_index, write_warnings

ACTION_EXTRACT = "extract"
ACTION_REGISTER = "register"
ACTION_UNCHANGED = "unchanged"
ACTION_SKIP = "skip"
ACTION_COLLISION = "collision"


@dataclass
class PlanItem:
    rel: str
    path: Path
    kind: Kind
    action: str
    size: int
    mtime_ns: int
    target: Path | None = None
    reason: str | None = None
    notes: list[str] = field(default_factory=list)
    prior: dict | None = None


@dataclass
class Plan:
    layout: Layout
    items: list[PlanItem]
    orphans: list[Path]
    mode_change: str | None = None
    ocr_note: str | None = None


@dataclass
class Report:
    layout: Layout
    records: list[Record]
    orphans: list[Path]
    pruned: list[Path]
    mode_change: str | None = None
    written: int = 0

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for record in self.records:
            out[record.status] = out.get(record.status, 0) + 1
        return out

    @property
    def failed(self) -> int:
        return self.counts.get(Status.FAILED.value, 0)


def _image_is_trivial(path: Path, size: int) -> bool:
    """spec §5.1：小于 200×200 像素或小于 20 KB 的图片当装饰跳过。"""
    if size < TRIVIAL_IMAGE_MIN_BYTES:
        return True
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        return False
    return width * height < TRIVIAL_IMAGE_MIN_PIXELS


def _classify(candidate: Candidate, cfg: Config, layout: Layout, prior: dict | None) -> PlanItem:
    kind, notes = identify(candidate.path)
    item = PlanItem(
        rel=str(candidate.rel),
        path=candidate.path,
        kind=kind,
        action=ACTION_EXTRACT,
        size=candidate.stat.size,
        mtime_ns=candidate.stat.mtime_ns,
        notes=notes,
        prior=prior,
    )

    if candidate.stat.size > cfg.max_bytes:
        item.action, item.reason = ACTION_SKIP, "too_large"
        return item
    if kind is Kind.UNKNOWN:
        item.action, item.reason = ACTION_SKIP, "unknown_type"
        return item
    if kind is Kind.UNSUPPORTED:
        item.action, item.reason = ACTION_SKIP, "unsupported"
        return item
    if kind is Kind.IMAGE:
        if not cfg.include_images:
            item.action, item.reason = ACTION_SKIP, "images_disabled"
            return item
        if _image_is_trivial(candidate.path, candidate.stat.size):
            item.action, item.reason = ACTION_SKIP, "trivial_image"
            return item

    if kind is Kind.PLAINTEXT:
        item.action = ACTION_REGISTER
        if cfg.mode is Mode.MIRROR:
            item.target = layout.text_root / str(candidate.rel)
    else:
        item.target = layout.text_path(candidate.rel)
    return item


def _fingerprint_hit(item: PlanItem, cfg: Config) -> bool:
    prior = item.prior
    if not prior or cfg.force:
        return False
    if prior.get("bytes") != item.size or prior.get("mtime_ns") != item.mtime_ns:
        return False
    if prior.get("config_digest") != cfg.content_digest():
        return False
    from .config import PIPELINE_VERSION

    if prior.get("pipeline_version") != PIPELINE_VERSION:
        return False
    if item.target is not None and not item.target.exists():
        return False
    return True


def _other_mode_manifest(cfg: Config) -> tuple[Manifest, Layout] | None:
    """模式切换检测：另一种模式的清单在别的路径上，必须主动去看一眼（spec §3.5 第 4 条）。"""
    if cfg.mode is Mode.MIRROR:
        other_meta = cfg.root / META_DIR_NAME
        other_mode = Mode.IN_PLACE
        text_root = cfg.root
    else:
        other_meta = cfg.root.parent / f"{cfg.root.name}{MIRROR_SUFFIX}"
        other_mode = Mode.MIRROR
        text_root = other_meta / "text"
    manifest = Manifest.load(other_meta / "MANIFEST.json")
    if not manifest.loaded or manifest.mode != other_mode.value:
        return None
    layout = Layout(root=cfg.root, mode=other_mode, meta_dir=other_meta, text_root=text_root)
    return manifest, layout


def _artifact_paths(manifest: Manifest, layout: Layout) -> list[Path]:
    return [layout.from_meta_rel(rel) for rel in manifest.artifacts]


def make_plan(cfg: Config) -> Plan:
    layout = Layout.from_config(cfg)
    manifest = Manifest.load(layout.manifest_path)

    known = set(_artifact_paths(manifest, layout))
    mode_change = None
    stale: list[Path] = []
    other = _other_mode_manifest(cfg)
    if other:
        other_manifest, other_layout = other
        stale = [p for p in _artifact_paths(other_manifest, other_layout) if p.exists()]
        known |= set(stale)
        if stale:
            mode_change = (
                f"上次以 `{other_manifest.mode}` 模式运行，留下 {len(stale)} 份产物；"
                "它们已成为孤儿，用 --prune 清理"
            )

    walker = Walker(cfg, layout, known_artifacts=known)
    items: list[PlanItem] = []
    for candidate in walker.walk():
        item = _classify(candidate, cfg, layout, manifest.record(str(candidate.rel)))
        items.append(item)

    items.sort(key=lambda it: it.rel)
    _resolve_targets(items, known)

    for item in items:
        if item.action in (ACTION_EXTRACT, ACTION_REGISTER) and _fingerprint_hit(item, cfg):
            item.action = ACTION_UNCHANGED

    expected = {str(it.target) for it in items if it.target}
    orphans = [
        path
        for path in _artifact_paths(manifest, layout)
        if str(path) not in expected and path.exists()
    ]
    orphans.extend(p for p in stale if str(p) not in expected)

    return Plan(layout=layout, items=items, orphans=sorted(set(orphans)), mode_change=mode_change)


def _resolve_targets(items: list[PlanItem], known: set[Path]) -> None:
    """两条护栏：同一目标不许被两份源文件抢；已存在的非生成物绝不覆盖（spec §3.5 第 3 条）。"""
    claimed: dict[Path, str] = {}
    for item in items:
        if item.target is None:
            continue
        target = item.target
        if target in claimed:
            item.action = ACTION_COLLISION
            item.reason = f"target_collision（与 {claimed[target]} 撞同一个输出路径）"
            item.target = None
            continue
        if target.exists() and target not in known and not is_generated(target):
            item.action = ACTION_COLLISION
            item.reason = "target_exists（目标已存在且不是本工具生成物，不覆盖）"
            item.target = None
            continue
        claimed[target] = item.rel


def _job_for(item: PlanItem, cfg: Config) -> Job:
    return Job(
        rel=item.rel,
        path=str(item.path),
        kind=item.kind.value,
        size=item.size,
        mtime_ns=item.mtime_ns,
        content_hash=content_hash(item.path),
        cfg=cfg,
    )


def _skip_record(item: PlanItem, cfg: Config) -> Record:
    status = Status.FAILED.value if item.action == ACTION_COLLISION else Status.SKIPPED.value
    return Record(
        rel=item.rel,
        kind=item.kind.value,
        status=status,
        bytes=item.size,
        mtime_ns=item.mtime_ns,
        skip_reason=item.reason,
        warnings=list(item.notes),
        config_digest=cfg.content_digest(),
    )


def build(cfg: Config, on_progress=None) -> Report:
    plan = make_plan(cfg)
    layout = plan.layout
    manifest = Manifest.load(layout.manifest_path)

    records: list[Record] = []
    artifacts: set[str] = set()
    written = 0

    work = [it for it in plan.items if it.action in (ACTION_EXTRACT, ACTION_REGISTER)]
    jobs = [_job_for(item, cfg) for item in work]
    targets = {item.rel: item.target for item in work}

    results: list[FileResult] = []
    ran_parallel = False
    if cfg.jobs > 1 and len(jobs) > 1:
        try:
            with ProcessPoolExecutor(max_workers=cfg.jobs) as pool:
                for result in pool.map(process, jobs):
                    results.append(result)
                    if on_progress:
                        on_progress(result.record)
            ran_parallel = True
        except (PermissionError, OSError, BrokenProcessPool):
            # 某些沙箱 / 容器禁用 POSIX semaphore。并发是性能优化，不该让正确性失败。
            results.clear()
    if not ran_parallel:
        for job in jobs:
            result = process(job)
            results.append(result)
            if on_progress:
                on_progress(result.record)

    for result in results:
        record = result.record
        target = targets.get(record.rel)
        if target is not None:
            if result.copy_from:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(result.copy_from, target)
            elif result.text is not None:
                write_atomic(target, result.text)
            record.text_rel = layout.rel_to_meta(target)
            artifacts.add(record.text_rel)
            written += 1
        records.append(record)

    for item in plan.items:
        if item.action == ACTION_UNCHANGED:
            prior = Record.from_dict(item.prior or {})
            prior.status = prior.status or Status.OK.value
            records.append(prior)
            if prior.text_rel:
                artifacts.add(prior.text_rel)
        elif item.action in (ACTION_SKIP, ACTION_COLLISION):
            records.append(_skip_record(item, cfg))

    pruned: list[Path] = []
    orphans = [p for p in plan.orphans if layout.rel_to_meta(p) not in artifacts]
    if cfg.prune:
        pruned = _prune(orphans, layout, cfg)
        orphans = [p for p in orphans if p not in pruned]

    manifest.root = str(layout.root)
    manifest.mode = cfg.mode.value
    manifest.out = str(layout.meta_dir)
    manifest.config_digest = cfg.content_digest()
    manifest.files = {r.rel: r.to_dict() for r in records}
    manifest.artifacts = sorted(artifacts)
    manifest.summary = {
        "files": len(records),
        "written": written,
        "orphans": len(orphans),
        "pruned": len(pruned),
    }
    manifest.save(layout.manifest_path)

    preamble: list[str] = []
    if plan.mode_change:
        preamble.append(plan.mode_change)
    if orphans:
        preamble.append(f"{len(orphans)} 份孤儿产物未清理，运行 `--prune` 删除")
    write_index(layout, records, cfg.mode)
    write_warnings(layout, records, preamble)

    return Report(
        layout=layout,
        records=records,
        orphans=orphans,
        pruned=pruned,
        mode_change=plan.mode_change,
        written=written,
    )


def _prune(orphans: list[Path], layout: Layout, cfg: Config) -> list[Path]:
    """只删登记在案且确实是自产的文件，且必须位于 root 或输出根之内。"""
    allowed_roots = [layout.root.resolve(), layout.meta_dir.resolve()]
    other = _other_mode_manifest(cfg)
    if other:
        allowed_roots.append(other[1].meta_dir.resolve())
    removed: list[Path] = []
    for path in orphans:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not any(resolved.is_relative_to(base) for base in allowed_roots):
            continue
        if not resolved.is_file():
            continue
        if not is_generated(resolved) and resolved.suffix.lower() == ".md":
            continue
        try:
            resolved.unlink()
            removed.append(path)
        except OSError:
            continue
    return removed


def status(cfg: Config) -> Report:
    layout = Layout.from_config(cfg)
    manifest = Manifest.load(layout.manifest_path)
    records = [Record.from_dict(data) for data in manifest.files.values()]

    orphans: list[Path] = []
    referenced = {r.text_rel for r in records if r.text_rel}
    for record in records:
        if not record.text_rel:
            continue
        source = layout.source_path(PurePosixPath(record.rel))
        target = layout.from_meta_rel(record.text_rel)
        if not source.exists() and target.exists():
            orphans.append(target)
    for rel in manifest.artifacts:
        if rel not in referenced:
            path = layout.from_meta_rel(rel)
            if path.exists():
                orphans.append(path)

    mode_change = None
    other = _other_mode_manifest(cfg)
    if other and manifest.loaded:
        stale = [p for p in _artifact_paths(other[0], other[1]) if p.exists()]
        if stale:
            mode_change = f"另有 {len(stale)} 份 `{other[0].mode}` 模式的产物残留"
            orphans.extend(stale)

    return Report(
        layout=layout,
        records=records,
        orphans=sorted(set(orphans)),
        pruned=[],
        mode_change=mode_change,
    )
