# 代码质量审查报告

> 审查日期：2026-02-20  
> 范围：`autowsgr/` 全部 Python 源文件  
> 类别：防御性编程滥用 + 接口迁移残留的冗余代码

---

## 一、本次已修复的问题

### 1.1 高优先级修复

#### ① `controller.py` — `assert` 用于运行时不变量验证

**位置**：`autowsgr/emulator/controller.py`，`connect()` 方法  
**原代码**：
```python
display = self._device.display_info
assert isinstance(display, dict)   # Python -O 模式下会被跳过
```
**问题**：`assert` 在以 `-O` 标志运行时会被 CPython 完全跳过，导致后续 `display.get("width")` 对非 dict 类型崩溃，且错误信息毫无诊断价值。  
**修复**：替换为显式 `if not isinstance(...): raise EmulatorConnectionError(...)` 并附带类型信息与 serial。

---

#### ② `controller.py` — `is_app_running()` 吞异常 + 内含 `assert`

**位置**：`autowsgr/emulator/controller.py`，`is_app_running()` 方法  
**原代码**：
```python
def is_app_running(self, package: str) -> bool:
    try:
        dev = self._require_device()
        ps_output = dev.shell("ps")
        assert isinstance(ps_output, str)   # ← assert 在 except Exception 内部
        running = package in (ps_output or "")
        return running
    except Exception:                        # ← 捕获了自己写的 AssertionError
        return False
```
**问题**：
1. `assert` 抛出的 `AssertionError` 被 `except Exception` 捕获，静默返回 `False`，调用方无法得知是设备断开还是程序逻辑错误。
2. `except Exception` 过宽，吞掉了 `AttributeError`、`TypeError` 等编程错误。

**修复**：
- 将 try/except 范围缩小到仅包含设备连接操作（`_require_device()` + `shell()`）。
- 捕获 `(AdbError, DeviceConnectionError, EmulatorConnectionError)` 具体类型，附带 `exc` 信息。
- `isinstance` 检查移出 try 块，作为普通逻辑处理。

---

#### ③ `controller.py` — `shell()` 静默返回空字符串掩盖 API 契约变化

**位置**：`autowsgr/emulator/controller.py`，`shell()` 方法  
**原代码**：
```python
def shell(self, cmd: str) -> str:
    dev = self._require_device()
    result = dev.shell(cmd)
    return result if isinstance(result, str) else ""   # ← airtest 返回非 str 时静默
```
**问题**：如果 airtest 内部升级导致 `dev.shell()` 返回非 `str`（如 `bytes`），此处会静默返回空字符串，上层调用方会将空命令输出当作"命令已运行无输出"处理，掩盖真实的契约变化。  
**修复**：替换为 `raise EmulatorConnectionError(...)` 并说明类型不符。

---

#### ④ `detector.py` — 注册表读取 `except OSError: pass`（无任何日志）

**位置**：`autowsgr/emulator/detector.py`，`_find_adb_from_registry()` 函数  
**原代码**（共 4 处）：
```python
    except OSError:
        pass        # ← PermissionError 也是 OSError 子类，无法区分
```
**问题**：
- `OSError` 的子类 `PermissionError` 表示注册表权限不足（非正常情况），与"注册表键不存在"的 `FileNotFoundError` 被一并静默。
- 当用户遭遇权限问题时，只会看到"未找到 adb"，没有任何可诊断的线索。

**修复**：改为 `except OSError as exc: logger.debug(...)` 并附带具体错误信息。

---

#### ⑤ `_os_linux.py` — `_adb_devices()` 完全静默失败

**位置**：`autowsgr/emulator/_os_linux.py`，`_adb_devices()` 方法  
**原代码**：
```python
        except Exception:
            return []
```
**问题**：`ImportError`（airtest 未安装）、`subprocess.CalledProcessError`（adb 执行失败）均被吞掉，返回空列表，上层代码误认为无在线设备。  
**修复**：缩窄到 `(ImportError, OSError, subprocess.CalledProcessError)`，加 `logger.debug` 记录原因。

---

### 1.2 中优先级修复

#### ⑥ `combat/plan.py` — `CombatPlan.repair_mode` 类型不一致

**位置**：`autowsgr/combat/plan.py`  
**问题**：`FightConfig`（Pydantic 模型）有 `_normalize_repair_mode` validator 保证 `repair_mode` 始终为 `list[RepairMode]`，但 `CombatPlan`（普通 dataclass）无对应处理，导致 `ops/normal_fight.py` 需要防御性 `isinstance` 分支。  
**修复**：为 `CombatPlan` 添加 `__post_init__` 归一化，保证字段始终为 `list[RepairMode]`。

---

#### ⑦ `ops/normal_fight.py` — 冗余 `isinstance` 分支

**位置**：`autowsgr/ops/normal_fight.py`，`_prepare_sortie()` 方法  
**原代码**：
```python
repair_modes = self._plan.repair_mode
if isinstance(repair_modes, list):
    min_mode = min(m.value for m in repair_modes)
else:
    min_mode = repair_modes.value
```
**修复**：删除 `isinstance` 分支，依赖 `CombatPlan.__post_init__` 的归一化保证。

---

#### ⑧ `ops/navigate.py` — 已弃用函数 `go_main_page()` 无调用方

**位置**：`autowsgr/ops/navigate.py`  
**问题**：函数文档标注"已弃用"，无任何内部调用方，`ops/__init__.py` 中也已注释掉其导出。  
**修复**：删除 `go_main_page()` 函数及模块 docstring 中的 deprecated 说明；同步更新 `ops/__init__.py` 中的注释行。

---

#### ⑨ `ui/page.py` — `get_current_page()` 返回 `None` 有歧义

**位置**：`autowsgr/ui/page.py`  
**问题**：原实现中，"无匹配"与"所有识别器均抛出异常"都返回 `None`，调用方无法区分两种情形。  
**修复**：引入 `failed_checkers: list[str]` 跟踪异常识别器，当存在错误识别器时升级日志级别为 `warning` 并列出出错识别器名称，与正常"无匹配"的 `debug` 日志明确区分。

---

## 二、未修复的遗留问题（需进一步讨论）

### 2.1 `FightResult` 与 `str` 的比较运算符

**位置**：`autowsgr/combat/history.py`，`FightResult.__lt__`/`__le__`  
**代码**：
```python
def __lt__(self, other: object) -> bool:
    if isinstance(other, FightResult): ...
    if isinstance(other, str):             # ← 允许 result < "S" 写法
        return self._grade_index() < self._GRADE_ORDER.index(other)
    return NotImplemented
```
**问题**：支持与裸 `str` 比较属于非必要的多态，增加 API 理解成本，且对不在 `_GRADE_ORDER` 中的字符串会抛出 `ValueError`。  
**建议**：移除 `str` 分支，调用方应始终使用 `FightResult` 枚举值比较。

---

### 2.2 `ops/decisive/_controller.py` — `except Exception` 吞掉所有错误

**位置**：`autowsgr/ops/decisive/_controller.py`，`run()` 方法  
```python
try:
    return self._main_loop()
except Exception:
    logger.exception("[决战] 执行异常")
    return DecisiveResult.ERROR
```
**问题**：任意未知异常（包括编程错误）均被转化为 `DecisiveResult.ERROR`，调用方无法区分"正常错误"与"bug"。  
**建议**：至少区分 `TimeoutError` / 已知业务异常与其他异常，对未知异常考虑向上抛出。

---

## 三、冗余代码（接口迁移后残留回退接口）

### 3.1 `vision/matcher.py` — 向后兼容重导出 `pixel.py` 类型

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/vision/matcher.py` 第 33–41 行 |
| **现象** | `Color`、`MatchStrategy`、`PixelDetail`、`PixelMatchResult`、`PixelRule`、`PixelSignature` 定义在 `pixel.py`，但 `matcher.py` 通过 `from pixel import ...` + `__all__` 重导出 |
| **背景** | 重构时将数据类从 `matcher.py` 迁移到 `pixel.py`，保留了 `matcher.py` 的兼容导出 |
| **调用方现状** | 全部调用方仍从 `autowsgr.vision.matcher` 导入，无直接使用 `pixel.py` 的外部代码 |
| **影响** | `matcher.py` 承担了"数据类型导出"与"匹配引擎"两个职责；`pixel.py` 的真正权威地位被掩盖 |
| **建议** | 将所有调用方批量改为 `from autowsgr.vision.pixel import Color, ...`；删除 `matcher.py` 的兼容重导出 |

---

### 3.2 `vision/image_matcher.py` — 向后兼容重导出 `image_template.py` 类型

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/vision/image_matcher.py` 第 26–44 行 |
| **现象** | `ROI`、`ImageTemplate`、`ImageRule` 等类型定义在 `image_template.py` 和 `roi.py`，但 `image_matcher.py` 通过 re-export 暴露 |
| **背景** | 同 3.1，数据类从 `image_matcher.py` 拆出到独立模块后保留了兼容出口 |
| **调用方现状** | 混乱：部分文件从 `image_matcher` 导入（`ops/reward.py`），部分直接从 `image_template` 导入（`ops/image_resources.py`），部分从 `roi.py` 导入（`ops/decisive/_handlers.py`） |
| **建议** | 统一导入路径：原始类型从各自模块导入；删除 `image_matcher.py` 的兼容重导出 |

---

### 3.3 `ui/page.py` — `noqa: F401` 隐式重导出 overlay 内容

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/ui/page.py` 第 50 行 |
| **现象** | `from autowsgr.ui.overlay import NetworkError, OverlayType, detect_overlay, dismiss_overlay  # noqa: F401` |
| **背景** | 重构时将这些符号从 `page.py` 迁移到 `overlay.py`，保留了重导出以兼容旧导入路径 |
| **调用方现状** | 无任何外部代码通过 `from ui.page import NetworkError` 导入；所有调用方均直接使用 `overlay.py` |
| **建议** | 删除此行 |

---

### 3.4 `ui/page.py` — `DEFAULT_TIMEOUT` / `DEFAULT_INTERVAL` 兼容常量

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/ui/page.py` 第 95–96 行 |
| **现象** | `DEFAULT_TIMEOUT: float = DEFAULT_NAV_CONFIG.timeout` 和 `DEFAULT_INTERVAL: float = DEFAULT_NAV_CONFIG.interval` |
| **背景** | 重构引入 `NavConfig` dataclass 后，原有裸常量未清理 |
| **调用方现状** | 仅 `testing/ui/page/test_unit.py` 引用，用于两行合理性断言 |
| **建议** | 将测试改为直接访问 `DEFAULT_NAV_CONFIG.timeout`；删除两个冗余常量 |

---

### 3.5 `combat/plan.py` vs `infra/config.py` — 双副本归一化逻辑

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/combat/plan.py`（`__post_init__`）与 `autowsgr/infra/config.py`（`_normalize_repair_mode`）|
| **现象** | 同样的"将单个 `RepairMode` 展开为 6 元素列表"逻辑在两处独立实现 |
| **建议** | 提取为公共工具函数 `_normalize_repair_mode_list(mode) -> list[RepairMode]` |

---

### 3.6 `controller.py` — 已注释的废弃 URI 行（已清理）

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/emulator/controller.py` |
| **现象** | `# uri = f"Android:///{resolved}" if resolved else "Android:///"` — 切换到 javacap 后的旧 URI 格式残留注释 |
| **状态** | ✅ 本次已删除 |

---

### 3.7 `ops/__init__.py` — 已注释的废弃导出（已清理）

| 项目 | 说明 |
|------|------|
| **文件** | `autowsgr/ops/__init__.py` |
| **现象** | `# "go_main_page",  # deprecated — use goto_page(ctrl, "主页面") instead` |
| **状态** | ✅ 本次已删除（连同 `go_main_page` 函数本体） |

---

## 四、汇总

### 已修复项目（9 项）

| # | 文件 | 问题 |
|---|------|------|
| 1 | `emulator/controller.py` | `assert isinstance(display, dict)` → 显式检查 |
| 2 | `emulator/controller.py` | `is_app_running` 吞异常 + 内含 assert |
| 3 | `emulator/controller.py` | `shell()` 静默返回空字符串 |
| 4 | `emulator/controller.py` | 删除废弃注释行 `# uri = ...` |
| 5 | `emulator/detector.py` | 4 处 `except OSError: pass` → 加 debug 日志 |
| 6 | `emulator/_os_linux.py` | `_adb_devices()` 静默失败 → 加日志 |
| 7 | `combat/plan.py` | 添加 `__post_init__` 归一化 `repair_mode` |
| 8 | `ops/normal_fight.py` | 删除冗余 `isinstance` 分支 |
| 9 | `ops/navigate.py` + `ops/__init__.py` | 删除弃用函数 `go_main_page` |
| 10 | `ui/page.py` | `get_current_page` 区分识别器错误与无匹配 |

### 待处理冗余项目（建议后续清理）

| 优先级 | 文件 | 问题 |
|--------|------|------|
| 🟠 中 | `vision/matcher.py` | 向后兼容重导出 `pixel.py` 类型 |
| 🟠 中 | `vision/image_matcher.py` | 向后兼容重导出 `image_template.py` 类型 |
| 🟠 中 | `ui/page.py` | `noqa: F401` 重导出 overlay 内容 |
| 🟡 低 | `ui/page.py` | `DEFAULT_TIMEOUT`/`DEFAULT_INTERVAL` 常量 |
| 🟡 低 | `combat/history.py` | `FightResult` 与 `str` 的比较支持 |
| 🟡 低 | `combat/plan.py` + `infra/config.py` | 双副本归一化逻辑 |
| 🟡 低 | `ops/decisive/_controller.py` | `except Exception → ERROR` 掩盖 bug |
