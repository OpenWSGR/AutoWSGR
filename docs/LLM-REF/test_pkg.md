# test_pkg - 视觉/OCR 回归测试套件

`test_pkg/` 是独立于 `testing/` 的截图驱动回归测试目录, 专门用于验证视觉识别、OCR、模板匹配等功能的准确性。

## 与 testing/ 的区别

| | `test_pkg/` | `testing/` |
|---|---|---|
| 框架 | 自定义 runner (`main()` 返回失败数) | pytest |
| 用途 | 视觉/OCR 截图回归测试 | 库代码单元测试 |
| 发现方式 | 子目录含 `tests.py` 由分发器扫描 | pytest 自动发现 `test_*.py` |
| 执行 | `python test_pkg/run_tests.py [name]` | `pytest testing/` |
| 测试数据 | PNG 截图 + config.py/data.json | pytest fixtures |

**例外**: `decisive_ocr/` 使用 pytest (文件名 `test_chapter_ocr.py`), 不被 `run_tests.py` 扫描, 需通过 `pytest test_pkg/decisive_ocr/` 单独运行。

## 运行方式

```bash
# 全部套件
python test_pkg/run_tests.py

# 指定套件
python test_pkg/run_tests.py blood node_tracker

# 单独运行某个套件
python test_pkg/blood/tests.py

# pytest 套件 (decisive_ocr)
pytest test_pkg/decisive_ocr/
```

## 分发器 run_tests.py

- 扫描 `test_pkg/` 下所有含 `tests.py` 的子目录
- 动态导入每个 `tests.py` 的 `main()` 函数
- `main()` 返回失败数量 (0 = 全部通过)
- 支持命令行参数按名称过滤套件
- ANSI 彩色输出, 汇总所有套件结果后 `sys.exit(0/1)`

## 套件一览

| 套件 | 测试目标 | 数据格式 | 状态 |
|---|---|---|---|
| blood | 舰船血量状态检测 | config.py (Python dict) | 正常 |
| decisive_ocr | 决战章节 OCR | pytest parametrize | 正常 (pytest) |
| detect_decisive_phase | 决战页面阶段检测 | 文件名约定 | 正常 |
| detect_fleet | 决战出征准备页舰队 OCR | data.json | 正常 |
| difficulty | 活动难度识别 | 代码内置 `_CASES` | 正常 |
| fleet_ocr | DLL + OCR 选船列表识别 | data.json | 正常 |
| image_resources | 图像模板匹配 | config.py (Python dict) | 正常 |
| level_rec | (无 tests.py) | 仅有截图 | 未完成 |
| loot_rec | 出征面板战利品/舰船数量 OCR | data.json + README | 正常 |
| misson_rec | 任务页面 OCR 识别 (名称+按钮) | data.json + images/ | 正常 |
| node_tracker | 小船位置追踪 | 文件名约定 | 正常 |
| recognize_node | 节点字母识别 (DLL) | 文件名约定 | 正常 |
| ui | 页面 is_current_page 识别 | 目录结构约定 | 正常 |

## 新增套件规范

### 1. 目录结构

```
test_pkg/<suite_name>/
  tests.py          <- 必须, 含 main() -> int
  config.py         <- 可选, Python 数据配置
  data.json         <- 可选, JSON 数据配置
  *.png             <- 测试截图
```

### 2. tests.py 模板

每个 `tests.py` **必须**遵循以下约定:

```python
"""<suite_name> 套件: <简短描述>。

<数据格式说明>

运行方式::

    python test_pkg/<suite_name>/tests.py
    python test_pkg/run_tests.py <suite_name>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import cv2

if TYPE_CHECKING:
    import numpy as np

# -- 确保项目根目录在 sys.path --
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SUITE_DIR = Path(__file__).resolve().parent

# -- 颜色常量 --
_GREEN = '\033[32m'
_RED = '\033[31m'
_CYAN = '\033[36m'
_YELLOW = '\033[33m'
_RESET = '\033[0m'
_BOLD = '\033[1m'
_PASS = f'{_GREEN}PASS{_RESET}'
_FAIL = f'{_RED}FAIL{_RESET}'


class _Result(NamedTuple):
    name: str
    passed: bool
    reason: str = ''


def _load_screen(path: Path) -> np.ndarray | None:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _run_case(...) -> _Result:
    """单个用例逻辑。"""
    ...


def main() -> int:
    """运行套件, 返回失败数量。"""
    print(f'\n{_BOLD}{_CYAN}{"─" * 60}{_RESET}')
    print(f'{_BOLD}套件: <suite_name>  (<描述>){_RESET}')
    print(f'{"─" * 60}{_RESET}')

    pass_count = fail_count = 0
    start = time.perf_counter()

    for ...:
        t0 = time.perf_counter()
        r = _run_case(...)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        status = _PASS if r.passed else _FAIL
        print(f'  {status}  {r.name:<35} {r.reason}  [{elapsed_ms:.1f}ms]')
        if r.passed:
            pass_count += 1
        else:
            fail_count += 1

    elapsed = time.perf_counter() - start
    total = pass_count + fail_count
    summary_color = _GREEN if fail_count == 0 else _RED
    print(
        f'\n{_BOLD}{summary_color}'
        f'  <suite_name>: {pass_count}/{total} 通过  失败={fail_count}  耗时={elapsed:.2f}s'
        f'{_RESET}'
    )
    return fail_count


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
```

### 3. 关键约定

- **`main()` 必须返回 `int`**: 失败数量, 0 = 全部通过。`run_tests.py` 依赖此返回值。
- **图片格式统一 RGB**: 使用 `cv2.imread` + `cv2.cvtColor(BGR2RGB)`, 与 `PixelChecker` 约定一致。
- **延迟导入 autowsgr**: 在 `_run_case` 或 `main` 内部导入, 避免模块加载时触发模拟器/OCR 初始化。
- **`_Result` 使用 `NamedTuple`**: 避免 `@dataclass` 在动态加载时的 `sys.modules` 问题 (Python 3.13+)。
- **颜色常量统一**: 使用 `_GREEN/_RED/_CYAN/_YELLOW/_RESET/_BOLD/_PASS/_FAIL`。
- **每个用例输出耗时**: `[{elapsed_ms:.1f}ms]`。
- **汇总行格式**: `<suite_name>: N/M 通过  失败=F  耗时=Xs`。

### 4. 数据格式选择

| 场景 | 推荐格式 |
|---|---|
| 期望值需引用 Python 对象 (枚举、模板等) | `config.py` |
| 纯字符串/数字期望值 | `data.json` |
| 文件名本身即期望值 (如 `A.png` -> 节点 A) | 文件名约定 |
| 正例/负例分类 | 目录结构 (`<PageName>/` + `<PageName>/false/`) |

### 5. 添加测试数据

1. 将截图放入套件目录 (1280x720 PNG)
2. 在 `config.py` / `data.json` / 或按命名约定添加期望值
3. 运行 `python test_pkg/run_tests.py <suite_name>` 验证

## 注意事项

- `level_rec/` 目前仅有截图, 无 `tests.py`, 不可运行
- `test_pkg/test_pkg/` 为空目录, 无实际用途
- `decisive_ocr/` 使用 pytest, 不被 `run_tests.py` 收录
- 部分套件依赖 DLL (recognize_node, fleet_ocr), 仅在 Windows 上可用
- OCR 初始化较慢 (EasyOCR), 套件内应复用引擎实例
