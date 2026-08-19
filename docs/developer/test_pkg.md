# test_pkg -- 视觉/OCR 回归测试图片库

## 概述

`test_pkg/` 是本地私有的视觉/OCR 回归测试集合，**不纳入版本控制**（已在 `.gitignore` 中排除），也不随 PyPI 包发布。

它与 `tests/` 的分工：

| 目录 | 作用 | 版本控制 | 框架 |
|------|------|----------|------|
| `tests/` | 单元测试、集成测试 | 是 | pytest |
| `test_pkg/` | 视觉/OCR 回归测试（含截图） | 否（本地私有） | 独立脚本 |

`test_pkg/` 中的测试图片来自游戏实机截图，体积较大且可能涉及版权，因此不适合入库。
每位开发者在本地维护自己的 `test_pkg/` 副本。

## 目录结构约定

每个测试套件一个子目录：

```
test_pkg/
├── run_all.py            <- 聚合运行器
├── <suite>/
│   ├── tests.py          <- 测试脚本（必须）
│   ├── data.json         <- 期望数据（推荐）
│   ├── *.png             <- 测试截图
│   ├── README.md         <- 套件说明（可选）
│   └── _debug_*.png      <- 调试辅助图片（可选）
```

嵌套一层也可以，如 `test_pkg/ui/MapPage/`。

## 数据格式

三种方式存储期望结果，按场景选择：

### 1. `data.json`（推荐）

文件名到期望值的 JSON 映射：

```json
{
    "0.png": {"loot": 0, "ship": 123},
    "1.png": {"loot": 23, "ship": 456}
}
```

字段不可识别时设为 `null`。适用于大多数 OCR/识别套件。

### 2. `config.py`

Python dict，适合枚举值等 JSON 表达不便的场景：

```python
data = {
    "1.png": ("prepare", ["NORMAL", "NORMAL", "SEVERE", "NO_SHIP", "NO_SHIP", "NO_SHIP"]),
}
```

### 3. 文件名约定

文件名即期望值，适合 1:1 映射（如 `CHOOSE_FLEET.png` 对应 `DecisivePhase.CHOOSE_FLEET`）。

## 测试脚本规范

所有套件使用**独立脚本模式**，不使用 pytest。

### `tests.py` 要求

1. 包含 `main() -> int` 函数，返回失败用例数量（0 = 全部通过）
2. 使用 ANSI 彩色输出标记 PASS/FAIL
3. `if __name__ == '__main__':` 入口调用 `main()` 并 `sys.exit`

### 模板

```python
"""<suite_name> 套件: <简要描述>。

运行方式::

    python test_pkg/<suite_name>/tests.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SUITE_DIR = Path(__file__).resolve().parent

_GREEN = '\033[32m'
_RED = '\033[31m'
_CYAN = '\033[36m'
_RESET = '\033[0m'
_BOLD = '\033[1m'
_PASS = f'{_GREEN}PASS{_RESET}'
_FAIL = f'{_RED}FAIL{_RESET}'


def _load_screen(path: Path):
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _run_case(filename: str, expected, **deps) -> tuple[bool, str]:
    img_path = _SUITE_DIR / filename
    if not img_path.exists():
        return False, f'文件不存在: {img_path}'

    screen = _load_screen(img_path)
    if screen is None:
        return False, f'无法解码图像: {img_path}'

    # TODO: 调用被测函数，比较结果
    return True, 'ok'


def main() -> int:
    print(f'\n{_BOLD}{_CYAN}{"=" * 60}')
    print(f'<suite_name>: <描述> ')
    print(f'{"=" * 60}{_RESET}')

    with open(_SUITE_DIR / 'data.json', encoding='utf-8') as f:
        data = json.load(f)

    fail_count = 0
    start = time.perf_counter()

    for filename, expected in sorted(data.items()):
        t0 = time.perf_counter()
        passed, reason = _run_case(filename, expected)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        tag = _PASS if passed else _FAIL
        print(f'  {tag}  {filename:<35}  {reason}  [{elapsed_ms:.0f}ms]')
        if not passed:
            fail_count += 1

    elapsed = time.perf_counter() - start
    total = len(data)
    color = _GREEN if fail_count == 0 else _RED
    print(
        f'\n{_BOLD}{color}'
        f'  <suite_name>: {total - fail_count}/{total} 通过'
        f'  失败={fail_count}  耗时={elapsed:.2f}s'
        f'{_RESET}\n'
    )
    return fail_count


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
```

## 运行方式

```bash
# 运行单个套件
python test_pkg/<suite>/tests.py

# 运行全部套件
python test_pkg/run_all.py

# 运行指定套件
python test_pkg/run_all.py blood loot_rec decisive_ocr
```

`run_all.py` 自动发现所有含 `tests.py` 的子目录，依次执行并输出汇总表。

## 新增套件步骤

1. 创建目录 `test_pkg/<suite_name>/`
2. 放入测试截图（PNG 格式）
3. 编写期望数据 `data.json`（或 `config.py`/文件名约定）
4. 复制上方模板到 `tests.py`，填充被测函数逻辑
5. 运行验证：`python test_pkg/<suite_name>/tests.py`

### 截图采集

使用 `tools/debug_screenshot.py` 进行截图和 OCR 调试：

```bash
# 截图并检查页面签名
python tools/debug_screenshot.py

# 对指定 ROI 区域做 OCR (相对坐标 x1,y1,x2,y2)
python tools/debug_screenshot.py --roi 0.818,0.81,0.875,0.867 --allowlist "0123456789Ex-"

# 从已有图片分析
python tools/debug_screenshot.py -i screenshot.png --roi 0.5,0.5,0.8,0.8
```

截图命名建议语义化（如 `decisive_page_ex6.png`），或使用 `pixel_marker_YYYYMMDD_HHMMSS.png` 工具默认格式。

## 现有套件一览

| 套件 | 目标 | 数据格式 |
|------|------|----------|
| `blood` | 舰船血量状态检测 | `config.py` |
| `decisive_ocr` | 决战章节编号 OCR | 脚本内嵌 |
| `detect_decisive_phase` | 决战页面阶段检测 | 文件名约定 |
| `detect_fleet` | 出征准备页舰队检测 | `data.json` |
| `difficulty` | 难度等级识别 | 脚本内嵌 |
| `fleet_ocr` | 舰队信息 OCR | `data.json` |
| `level_rec` | 出征准备页等级识别 | `data.json` |
| `loot_rec` | 战利品/舰船数量 OCR | `data.json` |
| `misson_rec` | 任务页面识别 | `data.json` |
| `mvp` | MVP 舰船识别 | `data.json` |
| `node_tracker` | 地图节点追踪 | 文件名约定 |
| `recognize_node` | 节点类型识别 | 文件名约定 |
| `repair` | 维修卡 OCR | `data.json` |
| `ship_drop` | 舰船掉落识别 | `data.json` |
| `ui/MapPage` | 地图页面识别 | `data.json` |
