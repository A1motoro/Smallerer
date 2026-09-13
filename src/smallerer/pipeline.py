"""单文件处理：抽取 → 归一 → 质检 → 渲染（spec §5.4–§5.7）。

这一层刻意只吃可序列化的输入、只吐可序列化的输出，好放进进程池；写盘留给主进程，
保证 MANIFEST 与原子替换只有一个写者。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config, Mode, OcrMode
from .manifest import Record
from .model import Document, ExtractError, Kind, Status
from .normalize import looks_mathy, normalize_page, strip_running_heads
from .quality import assess
from .writers import sidecar


@dataclass
class Job:
    rel: str
    path: str
    kind: str
    size: int
    mtime_ns: int
    content_hash: str
    cfg: Config


@dataclass
class FileResult:
    record: Record
    text: str | None = None
    copy_from: str | None = None


def _base_record(job: Job) -> Record:
    return Record(
        rel=job.rel,
        kind=job.kind,
        status=Status.OK.value,
        bytes=job.size,
        mtime_ns=job.mtime_ns,
        content_hash=job.content_hash,
        config_digest=job.cfg.content_digest(),
    )


def _ocr_notes(doc: Document, cfg: Config) -> list[str]:
    if not doc.pages_needing_ocr:
        return []
    count = len(doc.pages_needing_ocr)
    if doc.ocr_backend:
        return []
    if cfg.ocr is OcrMode.NEVER:
        return [f"{count} 页没有文字层，`--ocr never` 下未做识别。"]
    return [f"{count} 页没有文字层，本次运行没有可用的 OCR 后端，未做识别。"]


def process(job: Job) -> FileResult:
    started = time.perf_counter()
    record = _base_record(job)
    path = Path(job.path)
    kind = Kind(job.kind)

    if kind is Kind.PLAINTEXT:
        record.status = Status.REGISTERED.value
        record.text_layer = "n/a"
        record.extractor = "passthrough"
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        if job.cfg.mode is Mode.MIRROR:
            return FileResult(record=record, copy_from=job.path)
        return FileResult(record=record)

    from . import extractors

    try:
        extractor = extractors.get(kind)
        doc = extractor(path, job.cfg)
        if doc.pages_needing_ocr and job.cfg.ocr is not OcrMode.NEVER:
            from .ocr.service import apply as apply_ocr

            apply_ocr(doc, path, kind, job.cfg, job.content_hash)
    except ExtractError as exc:
        record.status = Status.FAILED.value
        record.quality = Status.FAILED.value
        record.skip_reason = exc.reason
        record.error = exc.message
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        return FileResult(record=record, text=_render_failure(record, exc))
    except Exception as exc:  # extractor 内部意外，同样必须可见
        record.status = Status.FAILED.value
        record.quality = Status.FAILED.value
        record.skip_reason = "extractor_error"
        record.error = f"{type(exc).__name__}: {exc}"
        record.duration_ms = int((time.perf_counter() - started) * 1000)
        return FileResult(record=record, text=_render_failure(record, exc))

    removed = strip_running_heads(doc.pages, keep=job.cfg.keep_running_heads)
    page_texts = [(p.number, p.source, normalize_page(p)) for p in doc.pages]
    report = assess([text for _, _, text in page_texts])

    record.extractor = doc.extractor
    record.pages = doc.total_pages or len(doc.pages)
    record.text_layer = doc.text_layer.value
    record.chars = report.chars
    record.chars_per_page_median = report.median_chars_per_page
    record.status = report.status.value
    record.quality = report.status.value
    record.has_tables = doc.has_tables
    record.has_math = doc.has_math or looks_mathy("\n".join(t for _, _, t in page_texts))
    record.partial = doc.partial
    record.removed_running_heads = removed
    record.warnings = list(doc.warnings) + report.reasons
    if doc.ocr_backend:
        record.ocr = {
            "backend": doc.ocr_backend,
            "pages": doc.ocr_pages,
            "chars": doc.ocr_chars,
        }
    if doc.image_heavy_pages:
        record.warnings.append(
            f"{len(doc.image_heavy_pages)} 页图像覆盖率超过 60%，纯文本可能丢信息"
        )

    notes = _ocr_notes(doc, job.cfg)
    record.warnings.extend(notes)
    record.duration_ms = int((time.perf_counter() - started) * 1000)

    text = sidecar.render(record, page_texts, notes, label=doc.page_label)
    return FileResult(record=record, text=text)


def _render_failure(record: Record, exc: Exception) -> str:
    note = record.error or str(exc)
    return sidecar.render(record, [], [f"抽取失败（{record.skip_reason}）：{note}"])
