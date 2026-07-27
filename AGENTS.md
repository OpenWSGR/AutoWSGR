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
