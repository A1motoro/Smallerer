# Smallerer

[![CI](https://github.com/A1motoro/Smallerer/actions/workflows/ci.yml/badge.svg)](https://github.com/A1motoro/Smallerer/actions/workflows/ci.yml)

把本地文档文件夹编译成适合 AI 助手读取、检索和引用的 Markdown 文本库。

项目仍在早期开发阶段，完整行为以 [`spec.md`](spec.md) 为准。

## 功能

- 支持 PDF、PPTX、DOCX 和图片文件
- 自动 OCR 识别无文字层页面（macOS Vision，Linux/Windows 会降级跳过）
- 两种输出模式：镜像模式（不改动源目录）和原地模式（文本贴在源文件旁）
- 幂等处理：只处理变化的文件，支持断点续传
- 页级 OCR 缓存，Ctrl-C 后可继续

## 系统要求

- Python 3.11 或更高版本
- macOS 10.15+ (用于 OCR，其他平台自动降级)

## 开发安装

```shell
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

## 使用

必须显式选择输出模式：

```shell
# 预览（不写盘）
smlr build ~/Documents/phys-notes --mirror --dry-run

# 镜像模式：在源目录旁建立 <源目录名>.ai-context/，不改动源目录
smlr build ~/Documents/phys-notes --mirror

# 原地模式：把 document.pdf.md 写在 document.pdf 旁边
smlr build ~/Documents/phys-notes --in-place

# 查看上次运行结果
smlr status ~/Documents/phys-notes
```

更多选项见 `smlr build --help`，包括：
- `--ocr {auto,never,only}`：控制 OCR 行为
- `--jobs N`：并发处理数
- `--prune`：删除孤儿产物（源文件已删除但生成物仍存在）
- `--force`：忽略指纹，全部重跑

## 配置文件

可选配置文件 `<源目录>/.smlr.toml` 或 `~/.config/smlr/config.toml`：

```toml
ocr = "auto"
jobs = 4
include_images = true
max_bytes = 536870912  # 512 MiB
max_ocr_pages = 500
```

命令行参数优先级高于配置文件。

## 隐私与版权

**重要提示**：

- **版权约束**：输出文本仍受原文件的版权或保密约定约束。本工具不改变文档的法律属性。
- **个人本机使用**：工具仅用于个人本机上下文，所有解析与 OCR 在你的设备上完成。
- **无云端处理**：不存在文档中转服务，不存在遥测，不上传任何文件内容。
- **不提供分享功能**：工具不提供分享包、同步或去水印功能。

使用本工具时，请遵守原文件的版权和保密协议。

