# Smallerer

把本地文档文件夹编译成适合 AI 助手读取、检索和引用的 Markdown 文本库。

项目仍在早期开发阶段，完整行为以 [`spec.md`](spec.md) 为准。

## 开发安装

```shell
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

## 使用

必须显式选择输出模式：

```shell
smlr build ~/Documents/phys-notes --mirror --dry-run
smlr build ~/Documents/phys-notes --mirror
smlr build ~/Documents/phys-notes --in-place
smlr status ~/Documents/phys-notes
```

- `--mirror`：在源目录旁建立 `<源目录名>.ai-context/`，不改动源目录。
- `--in-place`：把 `document.pdf.md` 写在 `document.pdf` 旁边，清单集中于 `_ai-context/`。

