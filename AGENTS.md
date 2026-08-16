# Agent Guidelines

## 安装

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
```

## pytest

```bash
pytest -n auto
```

测试目录结构：

| 目录 | 说明 |
|------|------|
| `tests/unit/` | pytest 自动运行的单元测试 |
| `tests/manual/` | 需真实设备的手动 e2e 测试 |

## pre-commit 检查

提交前务必运行：

```bash
pre-commit run --all-files
```

包含 **Ruff**（格式化与 lint）和 **ty**（类型检查）。

## 类型检查

本项目使用 **ty**（Astral 出品的 Python 类型检查器）进行静态类型检查。

- 优先通过正确的类型注解、返回值标注和类型窄化来消除类型错误。
- **禁止**在工作代码中使用 `typing.cast` 来掩盖类型问题；`cast` 只允许在测试文件的 Mock 场景中使用。
- 若类型检查器因容器型变（如 `list` 的 invariant）报错，优先考虑将函数参数改为 `Sequence`、`Mapping` 等协变抽象基类，而非使用 `cast`。
- 修复类型问题时尽量保持最小改动，避免不必要的重构。

### `ty: ignore` 注释规范

当必须通过注释忽略类型错误时，**必须使用 ty 原生格式**：

```python
# 正确
c.r = 10  # ty: ignore[invalid-assignment]
ctrl._device.shell.assert_called_once_with('input tap 480 270')  # ty: ignore[unresolved-attribute]

# 错误 —— ty 无法识别 mypy 的 error code
# type: ignore[invalid-assignment]
# type: ignore[misc]

# 错误 —— 裸 ignore 会被 ruff PGH003 拦截，且无法精确控制
# type: ignore
# type: ignore  # noqa: PGH003
```

> 项目已启用 `unused-type-ignore-comment = "error"`，未使用的 `# ty: ignore[...]` 会导致 CI 失败。

## 单元测试要求

新增功能或修改核心逻辑时，必须在 `tests/unit/` 下提供对应的 pytest 单元测试。测试文件应与被测源文件一一对应。

## 约定式提交

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
