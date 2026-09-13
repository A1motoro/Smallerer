"""命令行入口（spec §4）。"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from . import application
from .config import (
    MANIFEST_NAME,
    META_DIR_NAME,
    MIRROR_SUFFIX,
    Config,
    Mode,
    OcrMode,
    default_jobs,
    merge_config_sources,
)
from .manifest import Manifest
from .model import Status

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_MODE_HELP = """未指定输出模式。build 必须显式选一个，因为这个选择会实打实地改变你的目录：

  --mirror     另起一个与源目录结构相同的文件夹，源目录内零新增。
               默认位置是同级兄弟目录 <源目录名>.ai-context/，可用 --out 改。
               适合源目录在 iCloud / Dropbox / git 仓库里，或只读。

  --in-place   文本贴在每份源文件旁边（ch01-slides.pdf → ch01-slides.pdf.md），
               清单集中在 <源目录>/_ai-context/。适合想浏览原件时顺手看到文本版。

两种模式的产物可以互相切换，但切换后旧产物会成为孤儿，用 --prune 清理。
"""


def _size(text: str) -> int:
    units = {"k": 1024, "m": 1024**2, "g": 1024**3}
    raw = text.strip().lower().rstrip("ib")
    if raw and raw[-1] in units:
        return int(float(raw[:-1]) * units[raw[-1]])
    return int(float(raw))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smlr",
        description="把文档文件夹编译成给 AI 助手当 context 的文本库",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="扫描 → 抽取 → 写入，可重入")
    build.add_argument("root", type=Path)
    mode = build.add_mutually_exclusive_group()
    mode.add_argument("--mirror", action="store_true", help="另起一个镜像目录")
    mode.add_argument("--in-place", action="store_true", help="文本贴在源文件旁边")
    build.add_argument("--out", type=Path, default=None, help="镜像根（仅 --mirror）")
    build.add_argument("--dry-run", action="store_true", help="只打印计划，不写盘")
    build.add_argument("--ocr", choices=[m.value for m in OcrMode], default=None)
    build.add_argument("--jobs", type=int, default=None, help=f"并发进程数，默认 {default_jobs()}")
    build.add_argument("--force", action="store_true", help="忽略指纹，全部重跑")
    build.add_argument("--prune", action="store_true", help="删除孤儿产物")
    build.add_argument("--no-images", dest="include_images", action="store_false", default=None)
    build.add_argument("--include-images", dest="include_images", action="store_true")
    build.add_argument("--keep-running-heads", action="store_true", help="保留页眉页脚")
    build.add_argument("--max-bytes", type=_size, default=None)
    build.add_argument("--max-ocr-pages", type=int, default=None)
    build.add_argument("--follow-symlinks", action="store_true")

    status = sub.add_parser("status", help="读 MANIFEST 汇报上次结果，不动盘")
    status.add_argument("root", type=Path)
    status.add_argument("--out", type=Path, default=None)

    return parser


def _config_from_build(args: argparse.Namespace) -> Config:
    """从命令行参数和配置文件构建 Config（spec §4 优先级）。
    
    只有显式设置的 CLI 参数才覆盖 TOML 配置。
    """
    mode = Mode.MIRROR if args.mirror else Mode.IN_PLACE
    
    # 只传递显式设置的 CLI 参数（非 None/False）
    cli_overrides = {}
    if args.out is not None:
        cli_overrides["out"] = args.out
    if args.ocr is not None:
        cli_overrides["ocr"] = args.ocr
    if args.jobs is not None:
        cli_overrides["jobs"] = args.jobs
    if args.force:
        cli_overrides["force"] = True
    if args.prune:
        cli_overrides["prune"] = True
    if args.include_images is not None:
        cli_overrides["include_images"] = args.include_images
    if args.keep_running_heads:
        cli_overrides["keep_running_heads"] = True
    if args.follow_symlinks:
        cli_overrides["follow_symlinks"] = True
    if args.max_bytes is not None:
        cli_overrides["max_bytes"] = args.max_bytes
    if args.max_ocr_pages is not None:
        cli_overrides["max_ocr_pages"] = args.max_ocr_pages
    
    merged = merge_config_sources(args.root.expanduser(), cli_overrides)
    
    # 应用内置默认值
    return Config(
        root=args.root,
        mode=mode,
        out=Path(merged["out"]) if merged.get("out") else None,
        ocr=OcrMode(merged.get("ocr", "auto")),
        jobs=int(merged.get("jobs", 0)),
        force=bool(merged.get("force", False)),
        prune=bool(merged.get("prune", False)),
        dry_run=args.dry_run,
        include_images=bool(merged.get("include_images", True)),
        keep_running_heads=bool(merged.get("keep_running_heads", False)),
        follow_symlinks=bool(merged.get("follow_symlinks", False)),
        max_bytes=int(merged.get("max_bytes", 512 * 1024 * 1024)),
        max_ocr_pages=int(merged.get("max_ocr_pages", 500)),
    ).normalized()


def _infer_mode(root: Path, out: Path | None) -> Mode:
    if out is not None:
        return Mode.MIRROR
    in_place = Manifest.load(root / META_DIR_NAME / MANIFEST_NAME)
    if in_place.loaded and in_place.mode == Mode.IN_PLACE.value:
        return Mode.IN_PLACE
    mirror = Manifest.load(root.parent / f"{root.name}{MIRROR_SUFFIX}" / MANIFEST_NAME)
    if mirror.loaded and mirror.mode == Mode.MIRROR.value:
        return Mode.MIRROR
    return Mode.IN_PLACE


def _rel(path: Path, base: Path) -> str:
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return str(path)


def _print_plan(plan: application.Plan, cfg: Config) -> None:
    layout = plan.layout
    print(f"计划（{cfg.mode.value} 模式，未写盘）")
    print(f"  源目录：{layout.root}")
    print(f"  输出根：{layout.meta_dir}")
    if plan.mode_change:
        print(f"  ! {plan.mode_change}")
    print()

    width = max((len(it.rel) for it in plan.items), default=0)
    width = min(max(width, 12), 70)
    for item in plan.items:
        tail = ""
        if item.target:
            tail = f"→ {_rel(item.target, layout.meta_dir)}"
        elif item.reason:
            tail = item.reason
        print(f"  {item.action:<10}{item.rel:<{width}}  {tail}")

    counts = Counter(item.action for item in plan.items)
    print()
    print("汇总：" + "、".join(f"{name} {count}" for name, count in sorted(counts.items())))
    if plan.orphans:
        print(f"孤儿产物 {len(plan.orphans)} 份（--prune 可删）：")
        for path in plan.orphans[:20]:
            print(f"  {_rel(path, layout.meta_dir)}")


def _print_report(report: application.Report, cfg: Config) -> None:
    counts = report.counts
    layout = report.layout
    print()
    print(f"完成（{cfg.mode.value} 模式）")
    print(f"  输出根：{layout.meta_dir}")
    print(f"  入口：{layout.index_path}")
    order = [s.value for s in Status if s.value in counts]
    print("  " + "、".join(f"{name} {counts[name]}" for name in order))
    if report.pruned:
        print(f"  已清理孤儿 {len(report.pruned)} 份")
    if report.orphans:
        print(f"  ! 孤儿产物 {len(report.orphans)} 份未清理，运行 --prune 删除")
    if report.mode_change:
        print(f"  ! {report.mode_change}")
    problem = [
        r
        for r in report.records
        if r.status in {Status.FAILED.value, Status.EMPTY.value, Status.GARBLED.value}
    ]
    if problem:
        print(f"  详见 {layout.warnings_path}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        if not args.mirror and not args.in_place:
            print(_MODE_HELP, file=sys.stderr)
            return EXIT_USAGE
        if args.in_place and args.out is not None:
            print("--out 只对 --mirror 有意义；原地模式的清单固定在 <源目录>/_ai-context/", file=sys.stderr)
            return EXIT_USAGE
        if not args.root.expanduser().is_dir():
            print(f"不是目录：{args.root}", file=sys.stderr)
            return EXIT_USAGE

        try:
            cfg = _config_from_build(args)
        except (ValueError, RuntimeError) as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return EXIT_USAGE
        
        # spec §6.3 / §4: --ocr only 在没有后端时必须以退出码 2 失败
        if cfg.ocr is OcrMode.ONLY:
            from . import ocr
            if ocr.get_backend() is None:
                print(f"错误：{ocr.unavailable_reason()}", file=sys.stderr)
                print("--ocr only 要求有可用的 OCR 后端", file=sys.stderr)
                return EXIT_USAGE
        
        if cfg.mode is Mode.MIRROR and cfg.out is not None:
            if cfg.root == cfg.out or cfg.root.is_relative_to(cfg.out):
                print("镜像根不能是源目录本身或其祖先", file=sys.stderr)
                return EXIT_USAGE

        if cfg.dry_run:
            _print_plan(application.make_plan(cfg), cfg)
            return EXIT_OK

        done = 0

        def progress(record) -> None:
            nonlocal done
            done += 1
            print(f"  [{done}] {record.status:<10}{record.rel}")

        print(f"处理 {cfg.root}")
        report = application.build(cfg, on_progress=progress)
        _print_report(report, cfg)
        return EXIT_FAILED if report.failed else EXIT_OK

    if args.command == "status":
        root = args.root.expanduser()
        if not root.is_dir():
            print(f"不是目录：{args.root}", file=sys.stderr)
            return EXIT_USAGE
        cfg = Config(root=root, mode=_infer_mode(root.resolve(), args.out), out=args.out).normalized()
        report = application.status(cfg)
        if not report.records:
            print(f"没有找到清单：{report.layout.manifest_path}")
            return EXIT_OK
        _print_report(report, cfg)
        return EXIT_OK

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
