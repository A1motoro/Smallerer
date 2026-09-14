# 贡献指南

感谢对 Smallerer 的关注！

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/A1motoro/Smallerer.git
cd Smallerer

# 创建虚拟环境并安装依赖
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"

# 运行测试
./.venv/bin/python -m pytest -xvs
```

## 测试

所有更改必须包含测试。当前测试覆盖（44 个测试）：

- `tests/test_application.py` (10 tests) - 端到端应用逻辑、幂等性、孤儿检测
- `tests/test_cli.py` (3 tests) - 命令行接口、OCR 后端检查、TOML 配置
- `tests/test_concurrency.py` (5 tests) - 并发处理、进程池错误处理
- `tests/test_config.py` (6 tests) - 配置文件处理、优先级、合并逻辑
- `tests/test_index_sharding.py` (2 tests) - INDEX 分片（500+ 文件）
- `tests/test_normalize.py` (4 tests) - 文本归一化、软换行合并
- `tests/test_ocr_backend.py` (3 tests) - OCR 后端接口
- `tests/test_ocr_cache.py` (5 tests) - OCR 缓存与断点续传
- `tests/test_paths.py` (2 tests) - 路径解析、模式切换
- `tests/test_quality.py` (4 tests) - 质检逻辑、乱码检测

运行测试：

```bash
./.venv/bin/python -m pytest -xvs
```

## 测试 fixture

测试 fixture 由 `tests/make_fixtures.py` 自动生成。不要提交受版权保护的材料作为测试文件。

## 提交规范

- 使用清晰的中文或英文提交信息
- 每个逻辑更改一个提交
- 引用相关的 spec.md 章节

## PR 流程

1. 创建功能分支
2. 添加测试覆盖你的更改
3. 确保所有测试通过
4. 提交 PR，说明更改的动机和实现

## 代码风格

- 遵循现有代码风格
- 注释应该解释「为什么」而不是「做什么」
- 避免明显的、冗余的注释

## MVP 范围

当前处于 MVP 阶段（见 spec.md §9）。以下功能暂不接受：

- 跨平台 OCR 后端（§10 后续功能）
- 公式转 LaTeX
- 表格结构化
- GUI / 桌面应用
- 云解析或遥测

## 问题报告

报告问题时请提供：

- 操作系统和 Python 版本
- 完整的命令行和错误输出
- 最小可复现示例（如果可能）
- 不要上传受版权保护的文档

## 行为准则

保持友善和专业。我们欢迎所有建设性的贡献。
