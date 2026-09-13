# Smallerer — 项目规格

把磁盘上「给人看的大批量文档文件夹」编译成「给 AI 助手当 context 的文本库」。

输入是任意本地目录：论文合集、导出的笔记、项目文档、扫描件归档、幻灯片都可以。工具不关心这些文件从哪来，只关心它们已经在磁盘上。

- 项目名：**Smallerer**
- 命令名：**`smlr`**（`smallerer` 作为等价别名）
- 形态：Python CLI，开源发布，跨平台为目标（OCR 后端第一版仅 macOS，见 §6.3）

---

## 1. 要解决什么

助手擅长读文本，不擅长吞下成片的原文件。把一个文件夹直接丢进去时，常见情况是：

- PDF / PPTX 体积到 MB 甚至几十 MB，塞不进 context，或很快烧额度
- 真正有用的是文字；图片、装饰、页眉页脚、整页截图占掉预算
- 扫描件和「每页一张图」的幻灯片没有文字层，直接抽取得到空白
- 目录对人类有用，对「这一夹能不能当语料」并不友好：没有清单、没有跳过规则、不知道哪份已经抽过

目标产物不是更小的 PDF，而是**可检索、可引用页码的文本库**，体积以 KB 计。原件继续给人读；给模型的是文本。

---

## 2. 产品主张

1. **任意文件夹。** 用户指定根目录即可，不假设来源、不假设目录结构。
2. **原文件不动。** 只新增文件，绝不覆盖、删除或改写任何已存在的文件。新增位置由用户显式选择的输出模式决定（§3.1）。任何可能撞上用户文件的写入路径都必须报错，而不是覆盖。
3. **默认本机。** 解析与 OCR 全在用户机器上完成。不存在云端解析，也不存在遥测。
4. **失败可见。** 抽不出字就标记原因，绝不静默交空白文件。
5. **一次处理，多次使用。** 输出能直接 `@` 给 Cursor / Claude Code，或喂给本地 RAG，而不是每次都让助手重新解析原 PDF。
6. **可中断。** 大目录 OCR 要跑很久。任何时刻 Ctrl-C 或崩溃，下次运行从断点续跑。

这是文件夹编译器，不是下载器，不是压缩工具，也不是聊天产品。

---

## 3. 输出形态

### 3.1 两种输出模式

工具有且只有两种输出模式，**没有默认值**：`smlr build` 必须显式带 `--mirror` 或 `--in-place`，两者都不给时以退出码 2 退出并打印两种模式的区别。理由是这个选择会实打实地改变用户的目录，不该由默认值替他做。

**镜像模式 `--mirror`**：另起一个与源目录结构相同的文件夹，源目录内零新增。默认位置是源目录的同级兄弟目录 `<源目录名>.ai-context/`，`--out <dir>` 可改。

```text
~/Documents/
  phys-notes/                      ← 源目录，一个字节都不变
    syllabus.pdf
    lectures/ch01-slides.pdf
    lectures/ch01-notes.docx
    scans/handwritten-hw.jpg
  phys-notes.ai-context/           ← 新建的兄弟目录
    INDEX.md                       # 助手的默认入口：文件夹地图
    MANIFEST.json                  # 机器可读：指纹、extractor、状态、跳过原因
    WARNINGS.md                    # 无文字层、加密、损坏、过大、疑似乱码
    .cache/                        # 页级 OCR 缓存与断点，见 §5.5
    text/                          # 镜像源目录结构的文本库
      syllabus.pdf.md
      lectures/
        ch01-slides.pdf.md
        ch01-notes.docx.md
      scans/
        handwritten-hw.jpg.md
```

适用于源目录在 iCloud / Dropbox / git 仓库里，或是只读、不希望被写入的情况。

**原地模式 `--in-place`**：文本贴在每份源文件旁边，方便浏览原件时顺手看到文本版。三份清单仍集中在根目录下的 `_ai-context/`，不与内容混在一起。

```text
~/Documents/phys-notes/
  syllabus.pdf
  syllabus.pdf.md                  ← 新增
  lectures/
    ch01-slides.pdf
    ch01-slides.pdf.md             ← 新增
    ch01-notes.docx
    ch01-notes.docx.md             ← 新增
  scans/
    handwritten-hw.jpg
    handwritten-hw.jpg.md          ← 新增
  _ai-context/                     ← 仅清单与缓存，无内容
    INDEX.md
    MANIFEST.json
    WARNINGS.md
    .cache/
```

两种模式共用同一套管道，差别只在 writer 解析出的目标路径，以及 §3.5 列出的四条原地模式专属约束。

### 3.2 文本文件命名

**保留源文件全名再追加 `.md`**，即 `ch01-slides.pdf` → `ch01-slides.pdf.md`。两种模式都适用。这条规则是强制的，原因有三：同目录下的 `report.pdf` 与 `report.docx` 不会撞成同一个 `report.md`；用户自己写的 `ch01-slides.md` 与生成物永远不同名；原地模式下靠 `.<原扩展名>.md` 这个双后缀就能一眼认出哪些是生成物。

### 3.3 单份文本文件

每份产物是一个带 YAML 前置块的 Markdown：

```markdown
---
schema_version: 1
source_rel: lectures/ch01-slides.pdf
bytes: 52428800
content_hash: "blake2b256:9f2c…"
kind: pdf
pages: 42
extractor: "pymupdf@1.24.9"
text_layer: none
ocr:
  backend: "apple-vision@15.0"
  pages: [1, 2, 3, 4, 5, 6, 7, 8]
chars: 18420
chars_per_page_median: 430
quality: ok
has_math: true
has_tables: false
removed_running_heads: ["PHYS 201 — Fall 2026", "第 %d 页"]
warnings: []
generated_at: 2026-09-10T12:00:00+08:00
pipeline_version: "0.1.0"
---

# ch01-slides

> 本文件由 Smallerer 自动生成，源文件 `lectures/ch01-slides.pdf` 第 1–42 页。

## Page 1
<!-- page:1 ocr -->

（正文）

## Page 2
<!-- page:2 -->

（正文）
```

页锚点 `<!-- page:N -->` 是硬约定，供助手回答「这句出自哪」以及未来切 chunk 使用。OCR 得到的页额外带 `ocr` 标记，让读者知道这页文字是识别出来的、可能有错。

各类型的分块单位：PDF 用 `## Page N`；PPTX 用 `## Slide N`（含备注区）；DOCX 没有稳定页码，用原文标题层级 + `<!-- para:N -->` 段落序号；图片单文件只有一个 `## Page 1`。

### 3.4 INDEX.md

`INDEX.md` 是「把这个文件夹丢给 AI」时的默认入口，一份文件一行的紧凑表：路径、类型、页数、质量、是否建议纳入 context、跳过或降级的原因。

表里同时给出源文件路径与文本路径，两者都相对于 `INDEX.md` 自身。镜像模式下文本在 `text/` 下、源文件用相对路径回指源目录；原地模式下两者在同一个目录里。

超过 500 份文件时自动分片：`INDEX.md` 只保留按顶层子目录汇总的统计与导航，明细落到 `index/<subdir>.md`。这条规则的目的是让 INDEX 本身永远塞得进 context。

### 3.5 生成物的身份、孤儿与模式切换

一旦允许原地生成，「哪些文件是我们造的」就必须有可靠答案，否则第二次运行会把自己的产物当输入。四条规则：

1. **生成物登记。** MANIFEST 记录每一个写出去的路径。walker 遍历时排除这些路径。
2. **前置块兜底。** MANIFEST 丢失或损坏时，退化为读文件开头的 YAML 前置块：含 `pipeline_version` 字段的 Markdown 视为本工具生成物，跳过。
3. **绝不覆盖非生成物。** 写入前若目标已存在且两条判据都不认它，报错并跳过该文件，不覆盖、不改名重试。
4. **孤儿与模式切换。** 源文件被删除或改名后，旧生成物成为孤儿；从一种模式切到另一种时，上一批产物同样成为孤儿。`status` 必须列出孤儿清单；`build --prune` 删除它们，且只删 MANIFEST 记录在案的自产文件。MANIFEST 记录本次使用的模式，检测到模式变更时打印警告并提示 `--prune`。

### 3.6 体积预期

- 有文字层的短文档：数 KB 到数十 KB
- 有文字层的长 PDF：数十 KB 到一两百 KB
- OCR 出来的截图型幻灯片：每页数百字到两千字
- OCR 失败或未启用时：文本文件只有前置块 + 一行说明，**不允许**产出看起来成功的长空文

---

## 4. 命令面

第一版只有两个命令。`scan` / `plan` 不单独存在——它们的产物就是 `build --dry-run`，拆开只会让实现重复。

```text
smlr build  <root> (--mirror | --in-place) [选项]   # 扫描 → 抽取 → 写入，可重入
smlr status <root> [--out DIR]                      # 读 MANIFEST，汇报上次结果，不动盘
```

`build` 的选项：

| 选项 | 默认 | 说明 |
|---|---|---|
| `--mirror` / `--in-place` | **无默认，必选其一** | 输出模式，见 §3.1。两者互斥；都不给则退出码 2 |
| `--out DIR` | `<root>/../<root名>.ai-context`（仅 `--mirror`） | 镜像根。与 `--in-place` 同时给出时报错 |
| `--dry-run` | 关 | 只扫描并打印计划（每份文件将被如何处理、写到哪个路径、预计 OCR 页数），不写任何盘 |
| `--ocr MODE` | `auto` | `auto` 逐页判断 / `never` 跳过 OCR 只抽文字层 / `only` 只补做此前标记为需 OCR 的页 |
| `--jobs N` | `min(8, cpu_count)` | 并发进程数 |
| `--force` | 关 | 忽略指纹，全部重跑 |
| `--prune` | 关 | 删除孤儿生成物，见 §3.5。只删 MANIFEST 记录在案的自产文件 |
| `--include-images / --no-images` | 开 | 是否处理独立图片文件 |
| `--keep-running-heads` | 关 | 保留页眉页脚，不做跨页去重（见 §5.6 第 4 条） |
| `--max-bytes N` | `512MiB` | 单文件体积上限，超过标记跳过 |
| `--max-ocr-pages N` | `500` | 单文件 OCR 页数上限，超过标记 `partial` |
| `--follow-symlinks` | 关 | 是否跟随符号链接 |

`build` 除「未指定模式」外**不需要任何交互确认**，可直接用于脚本。预览靠 `--dry-run`。

退出码：`0` 全部成功或仅有正常跳过；`1` 存在失败文件（其余仍已写入）；`2` 参数或环境错误（未指定模式、目录不存在、无 OCR 后端而 `--ocr only`）。

配置优先级：命令行 > `<root>/.smlr.toml` > `~/.config/smlr/config.toml` > 内置默认。配置文件全部可选，工具不主动创建它们。

---

## 5. 处理管道

### 5.1 遍历与忽略

递归遍历根目录。默认跳过：

- 输出目录本身，以及镜像根若恰好位于根目录内
- 本工具的生成物，判据见 §3.5（原地模式下这条是必需的，否则第二轮会把上一轮的 `.md` 当输入）
- 以 `.` 开头的文件与目录
- `node_modules/`、`__pycache__/`、`.venv/`、`.git/`
- 符号链接（除非 `--follow-symlinks`）
- 小于 200×200 像素或小于 20 KB 的图片（`skipped: trivial_image`，通常是图标与装饰）

不读取 `.gitignore`（语义不同）。支持根目录下可选的 `.smlrignore`，语法与 gitignore 一致。

### 5.2 识别

扩展名优先，magic bytes 校验。两者冲突时以 magic bytes 为准并记录警告（常见于改过扩展名的文件）。识别不出的类型登记为 `skipped: unknown_type`，不猜测、不尝试当纯文本读。

### 5.3 幂等

幂等键 = `content_hash` + `pipeline_version` + 影响输出的配置摘要。三者任一变化即重跑。

快路径：`size` 与 `mtime_ns` 都与 MANIFEST 记录一致时，跳过哈希计算直接判定未变。否则用 BLAKE2b-256 全文件哈希（80 MB 文件约 0.1 秒，不需要采样策略）。

### 5.4 抽取

按类型分派 extractor，见 §6。抽取阶段只做保真提取，不做摘要、不做翻译、不做改写。

### 5.5 OCR（页级）

`--ocr auto` 下，逐页判断：某页文字层的非空白字符数 `< 30`（`ocr_page_threshold`）则该页走 OCR，OCR 结果作为该页正文，页号记入 `ocr.pages`；否则用文字层。因此电子版论文里夹着的几页扫描件会被自然处理，无需整份文件二选一。

页面图像覆盖率只用于质检标记（`image_heavy_pages`），**不**触发 OCR——避免同一页同时输出文字层和 OCR 结果造成重复内容。

光栅化默认 200 DPI（Vision 在此分辨率对中英文均足够），单页像素上限 4000×4000。

**页级缓存与断点**：每页 OCR 结果按 `content_hash + page_no + ocr 配置摘要` 存进 `_ai-context/.cache/ocr/`。中途 Ctrl-C 或崩溃后重跑，只处理没做过的页。缓存是纯派生数据，删掉只会变慢，不会丢正确性。

并发按文件粒度分配到 `--jobs` 个进程；每个进程独立初始化 OCR 后端。

### 5.6 归一化

中英混排是这一步的主要难点，规则必须确定：

1. 统一 UTF-8、LF 换行、行尾去空白，连续空行压缩到最多一个
2. 软换行合并，按顺序判断：
   - 前行以句末标点（`。！？；：.!?;:`）结尾 → 保留换行
   - 前行长度短于本页行长中位数的 60% → 视为标题或列表项，保留换行
   - 前行末尾与后行开头都是 CJK 字符 → 直接拼接，**不插空格**
   - 前行以 `-` 结尾且其前为拉丁字母、后行以小写拉丁字母开头 → 去掉连字符拼接
   - 前行末尾为拉丁字母或逗号，后行以小写拉丁字母开头 → 用单个空格拼接
   - 其余情况保留换行
3. 不在 CJK 与拉丁/数字之间强行插入空格（那是改写原文，不是归一化）
4. 页眉页脚去重（`--keep-running-heads` 可关）：跨页重复出现 ≥ 3 次、且位于页面上下各 8% 区域的相同短行予以移除。OCR 页没有可靠坐标，退化为纯文本频次判断（重复次数 ≥ `max(3, 页数 × 0.5)`）。被移除的内容必须完整列在 `removed_running_heads` 里——去掉了什么要可见。

### 5.7 质检

每份文件产出一个 `quality`，取值与判据完全确定：

| quality | 判据 |
|---|---|
| `ok` | 不满足下列任一条件 |
| `low` | 页均非空白字符中位数 `< 100`，或总字符数 `< 200` |
| `empty` | 总非空白字符数 `< 50` |
| `garbled` | 见下 |
| `failed` | 抽取抛错（加密、损坏、依赖缺失） |

`garbled` 判据满足其一即可：U+FFFD 替换字符占比 `> 1%`；Unicode 私用区或不可打印字符占比 `> 5%`；以拉丁字符为主且平均 token 长度 `< 1.5`（PDF 的 CID 字体映射损坏时典型表现为逐字母分隔）。

`low` / `empty` / `garbled` / `failed` 全部写入 `WARNINGS.md`，并在 `INDEX.md` 里标注为「不建议纳入 context」。

### 5.8 写入

先写临时文件再原子替换，临时文件与目标同分区，避免跨设备 rename 失败。目标路径的存在性检查按 §3.5 第 3 条执行。

MANIFEST 每完成一批文件落盘一次，保证中断后不丢进度。

---

## 6. 抽取策略

### 6.1 PDF

主战场。

| 情况 | 做法 | 结果 |
|---|---|---|
| 页有可用文字层 | PyMuPDF 抽字，按页切块 | KB 级文本 |
| 页文字 `< 30` 字符 | 该页光栅化后走 OCR（`--ocr auto`） | 页正文来自 OCR，标 `ocr` |
| 加密（需口令） | 记 `failed: encrypted`，不尝试破解，不重试 | 只有前置块 + 说明 |
| 结构损坏 | 记 `failed: corrupt`，尽量抽出可读页 | 部分内容 + 警告 |
| 超过 `--max-bytes` | 记 `skipped: too_large`，不读入 | 只登记到 INDEX |

明确不做：「删掉 PDF 里的图片另存一个瘦 PDF」。瘦 PDF 对助手仍然不友好，且会连图注一起丢。

### 6.2 其它类型

| 类型 | 第一版 | 说明 |
|---|---|---|
| `.pptx` | 做 | 形状文字 + 演讲者备注；纯图页走 OCR |
| `.docx` | 做 | 正文 + 标题层级 |
| `.png .jpg .jpeg .webp .tiff .heic` | 做 | 直接 OCR；小图按 §5.1 跳过 |
| `.md .txt .csv` | 登记 | 一律编入 INDEX，绝不「简化」内容。镜像模式下**复制**一份到 `text/`（保证整个镜像目录自足、可整夹拷走）；原地模式下**只登记**，因为原文件就在旁边，复制毫无意义 |
| `.xlsx` | 不做 | 登记为 `skipped: unsupported` |
| `.html` | 不做 | 同上 |
| 音视频 | 不做 | 不属于文档 context |

### 6.3 OCR 后端

第一版实现 **Apple Vision**（通过 PyObjC 调用系统框架），理由是零额外依赖、中英混排识别质量高、纯本机。

OCR 写成可插拔接口 `OcrBackend.recognize(image) -> list[TextBlock]`。非 macOS 平台第一版没有可用后端，行为必须明确：`--ocr auto` 降级为 `never` 并在 WARNINGS 顶部打印一条说明；`--ocr only` 直接以退出码 2 失败。跨平台后端（RapidOCR / PaddleOCR / Tesseract）是接口的第二个实现，不改变管道。

### 6.4 明确不走的路

- 把文件上传到自建服务或商业解析 API
- 用模型把整份文档压成一段摘要就当成功（摘要丢失可引用的细节，与「当 context」不是同一需求）

模型摘要可以是后续的独立命令（`smlr distill`），必须与 `build` 产物分开目录，且默认使用用户自己的 API key。

---

## 7. 已知会做不好的地方

这些是纯文本方案的固有损失。第一版**不解决**，但必须**可见**（写进前置块与 INDEX），并在代码里留好接口。不允许静默产出错误内容。

| 难点 | 第一版行为 | 预留的扩展点 |
|---|---|---|
| 数学公式 | 按原样抽出（常见结果是符号错位或丢上下标）。检测页内数学符号密度，命中则 `has_math: true`，INDEX 标注「公式页，文本可能失真」 | `extractors/math/` 接口，后续接 pix2tex / Nougat / 视觉模型逐页转 LaTeX |
| 表格 | 用 PyMuPDF 的表格检测做 best-effort 转 Markdown 表；置信度低或跨页表则保留原始文本行并置 `has_tables: true` + 警告 | `extractors/table/` 接口，后续接专用表格识别模型 |
| 中英混排断行 | 按 §5.6 的确定规则合并，规则本身可配置 | 归一化写成规则链，可整条替换 |
| 双栏 / 多栏版面 | 不做栏识别，按 PyMuPDF 阅读顺序输出，可能串行 | `layout/` 接口，后续接版面分析 |
| 手写内容 | OCR 照跑，准确率低；若质检命中 `garbled` 则降级 | 与 OCR 后端同一接口 |
| 幻灯片里的图表 | 纯文本必然丢失，不生成占位描述 | 后续可选：视觉模型生成图注 |

---

## 8. 技术选型与架构

Python CLI。选它是因为 PDF/Office 生态最成熟，且 PyObjC 能直接调 Vision，不需要额外的 Swift 辅助程序。代价是分发依赖 `uv` 或 PyInstaller，比单二进制麻烦一层。

依赖方向（实现时锁版本）：

- PDF：PyMuPDF
- Office：python-pptx、python-docx
- OCR：PyObjC（Vision / Quartz）
- 清单与配置：JSON 与 TOML，不引入数据库
- 哈希：标准库 `hashlib.blake2b`

分层：

```text
cli
  → application（build / status / dry-run 计划）
    → walker（遍历、忽略规则、指纹）
    → extractors（pdf, pptx, docx, image, passthrough）
      → ocr backends（apple-vision, …）
    → normalize（编码、软换行、页眉页脚）
    → quality
    → writers（text sidecar, index, manifest, warnings）
```

extractor、OCR 后端、归一化规则三者都必须能单独测试。

**测试 fixture 全部由脚本生成，不提交任何受版权材料**：用 ReportLab 造有文字层 PDF；把同一份文本渲染成图片再打包成 PDF，得到无文字层样本；用 python-docx / python-pptx 造 Office 样本；人为破坏字节得到损坏样本；加口令得到加密样本。中英混排、公式、双栏各造一份，用于回归。

---

## 9. MVP 范围

做：

- 指定文件夹，递归扫描，按 §5.1 忽略
- 镜像与原地两种输出模式，含生成物识别、孤儿检测、`--prune`
- PDF / PPTX / DOCX / 图片抽取，页级 OCR（macOS）
- 写文本文件、`INDEX.md`、`MANIFEST.json`、`WARNINGS.md`
- 幂等：源文件与配置未变则跳过；OCR 页级缓存与断点续跑
- 质检按 §5.7 的确定阈值，结果全部可见
- `--dry-run` 预览；按文件汇报进度与失败
- 并发处理

不做：

- 跨平台 OCR 后端
- 公式转 LaTeX、表格结构化、双栏版面还原
- xlsx / html
- 云解析、遥测、账号系统
- 向量库、chunk、embedding
- 自动摘要、自动翻译
- 常驻 daemon、系统资源管理器集成、桌面 GUI

验收标准：

1. 有文字层的 PDF：文本人能读、助手能按页引用，体积从 MB 落到 KB
2. 整页截图的 PDF：OCR 后有可用中英文文本；OCR 不可用时不产生看起来成功的长空文，WARNINGS 里有明确原因
3. 混合文档（电子版夹几页扫描件）：只有扫描页走 OCR，页号在前置块中列出
4. 重复运行不产生第二份内容，只更新变化检测；OCR 全部命中缓存
5. OCR 跑到一半 Ctrl-C，重跑时从未完成的页继续，不从头开始
6. 镜像模式下源目录零字节改动；原地模式下源目录只多出 `.<扩展名>.md` 与 `_ai-context/`，原有文件一律不被触碰
7. 原地模式连跑两次，第二次不把上一次的产物当输入，文件总数不变
8. 删掉一份源文件后 `status` 报出孤儿，`--prune` 只删该孤儿
9. 只把镜像目录丢给助手，不附带原 PDF，也能回答文档级问题

---

## 10. 之后可以加，但不要污染 MVP

| 阶段 | 内容 | 退出条件 |
|---|---|---|
| 跨平台 OCR | RapidOCR / Tesseract 后端 | Linux / Windows 上行为与 macOS 一致 |
| 公式 | 逐页转 LaTeX | 公式页文本可被助手正确复述 |
| 表格 | 专用表格识别 | 跨页表不再错位 |
| 版面 | 双栏 / 多栏阅读顺序 | 论文不再串行 |
| distill | 可选 LLM 摘要 | 与 build 产物分开目录，不覆盖保真文本 |
| chunk | 按页 / 标题切块导出给 RAG | 纯派生，不需重跑抽取 |
| watch | 监视根目录增量 build | 只处理变化 |
| desktop | 选文件夹 + 进度 UI | CLI 行为不变 |

---

## 11. 隐私与合规

- 所有解析与 OCR 在用户机器上完成，不存在文档中转服务，也不存在遥测。
- 日志只记录文件名、大小、extractor、错误码，不写文件正文。
- 若未来提供 `distill`，密钥只存本机配置，请求直达用户选择的提供方，本项目不代收文件。
- README 必须说明：输出文本仍受原文件的版权或保密约定约束。工具只服务个人本机上下文，不提供分享包、同步或去水印。

---

## 12. 起步顺序

1. `walker` + 识别 + 指纹 + 路径解析（两种模式）+ `--dry-run`：先让「这一夹里有什么、每份会写到哪」完全正确，不写盘。
2. PDF 文字层 extractor + 归一化 + 质检 + writers：先只做镜像模式，跑通完整闭环。
3. 原地模式：生成物识别、孤儿检测、`--prune`。连跑两次必须稳定。
4. 页级 OCR 与缓存断点：这是最耗时的一块，单独做。
5. PPTX / DOCX / 图片。
6. INDEX 分片、并发、错误处理打磨。

不要在第一周同时做 OCR 和 GUI。
