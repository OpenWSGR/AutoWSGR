# Agent Guidelines

## 开发环境

```bash
git clone git@github.com:OpenWSGR/AutoWSGR.git
cd AutoWSGR
uv sync
pre-commit install
```

激活虚拟环境后可直接运行命令（无需 `uv run` 前缀）：

```bash
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pytest
pre-commit run --all-files
```

## 代码风格

- Python 版本：3.12+
- 格式化与 lint：**Ruff**（已覆盖 isort / black 功能），配置见 `pyproject.toml`
- 目标行宽 100，单引号字符串
- 禁止相对导入（`ban-relative-imports = all`）
- 英语拼写检查：**codespell**，忽略词表见 `docs/spelling_wordlist.txt`

提交前务必运行：

```bash
pre-commit run --all-files
```

## 测试

- 单元测试：`pytest`（测试目录 `testing/`）
- 功能测试：运行 `examples/` 目录中的脚本进行端到端验证

```bash
pytest
```

## 约定式提交（Conventional Commits）

提交信息格式：

```
<type>(<scope>): <简短描述>

<正文>
```

常用类型：

- `feat`：新功能
- `fix`：修复
- `build`：构建系统或依赖变更
- `docs`：文档
- `style`：不影响代码逻辑的格式调整
- `refactor`：重构
- `test`：测试

示例：

```
build: migrate from setuptools to hatchling

- Replace setuptools with hatchling as build backend
- Remove obsolete MANIFEST.in
```

## 构建与打包

- Build backend：**hatchling**
- 包数据（图片、YAML、JAR 等）位于 `autowsgr/data/`，由 hatchling 自动包含，无需 `MANIFEST.in`

```bash
uv build
```

## 文档

- 用户文档地址：https://docs-autowsgr.notion.site
- 代码变更后同步更新文档，并鼓励在代码中编写注释和文档字符串。

## ShiinaKuroko Fork 分支管理

本仓库的个人 Fork 为 `https://github.com/ShiinaKuroko/AutoWSGR.git`。后续 Agent
必须遵守以下分支职责，不得自行改变分支用途：

- `main` 只用于同步 `OpenWSGR/AutoWSGR:main`，禁止在该分支直接开发、提交或推送功能代码。
- `ShiinaKuroko` 是个人 Fork 的最新开发分支，经过验证的最新代码才允许推送到这里。
- `backup/YYYYMMDD-<short-sha>` 是版本备份分支。每次更新 `ShiinaKuroko` 前，先创建一个指向更新前稳定提交的备份；完成更新后，再创建一个指向新稳定提交的备份，最多保留两个备份分支。
- 备份分支一旦创建不得移动、覆盖或追加提交。超过两个备份时，只删除最旧的备份分支，不删除当前备份和上一个备份。
- Agent 临时分支、worktree 分支和实验分支不得直接推送到 `main` 或冒充 `ShiinaKuroko`；任务完成后应删除不再需要的临时远程分支。
- 推送前必须确认工作树、提交范围和目标分支：`git status --short --branch`、`git diff --check`、`git log --oneline -5`。
- 推送最新代码前必须先创建备份，并使用 `git push --force-with-lease` 更新 `ShiinaKuroko`，禁止无条件 `--force`。
- 任何删除远程分支的操作都必须先列出将被删除的分支、提交和原因；禁止删除 `main`、`ShiinaKuroko` 或未明确授权的分支。
- 新功能必须在独立分支或 worktree 中开发，完成测试后才能合并或推送到 `ShiinaKuroko`。
- 本地独立开发分支只能用于编码、测试和审查，禁止直接推送到 Fork 的任何发布分支。
- 本地独立分支完成后，必须将已验证提交合并、cherry-pick 或 rebase 整理到本地 `ShiinaKuroko` 分支；只有本地 `ShiinaKuroko` 分支允许执行 `git push origin ShiinaKuroko`。
- 不得执行 `git push origin <local-feature-branch>` 作为发布流程；远程临时分支如确有协作需要，必须获得明确授权，并不得替代 `ShiinaKuroko` 发布入口。
- 推送前必须确认当前分支为本地 `ShiinaKuroko`，且 `git log origin/ShiinaKuroko..ShiinaKuroko` 只包含本次计划发布的提交。
- 后端发布至少执行 `pytest -q` 和 `git diff --check`；无法执行的检查必须在交付说明中明确记录。
