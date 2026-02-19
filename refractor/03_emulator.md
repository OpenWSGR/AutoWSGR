# 模拟器操作层 (Emulator)

> **状态**: ✅ **已完成** — 322 tests passing (含 72 emulator tests)

## 职责

提供 **纯粹的设备控制**：连接、截图、点击、滑动、键入、应用管理。

**不做**任何图像匹配、页面识别或游戏逻辑判断。

---

## 现状问题（已解决）

原 `AndroidController` (~470 行) 混杂了：
- 设备操作：`click()`, `swipe()`, `update_screen()`, `get_screen()`
- 图像匹配：`image_exist()`, `wait_image()`, `wait_images()`, `click_image()`
- 像素检查：`check_pixel()`, `get_pixel()`

**V2 解决方案**：
- 图像匹配相关方法已移至 Vision 层（`PixelChecker`）
- 控制器仅保留纯设备操作
- 所有坐标使用 **相对值 (0.0–1.0)**，不再使用 960×540 固定分辨率

---

## 已实现文件

### `autowsgr/emulator/controller.py`

```python
@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """已连接设备的基本信息。"""
    serial: str
    resolution: tuple[int, int]  # (width, height)


class AndroidController(ABC):
    """Android 设备控制器抽象基类 — 13 个抽象方法。"""

    # 连接管理
    def connect(self) -> DeviceInfo: ...
    def disconnect(self) -> None: ...
    @property
    def resolution(self) -> tuple[int, int]: ...

    # 截图 — 返回 BGR uint8 ndarray (H, W, 3)
    def screenshot(self) -> np.ndarray: ...

    # 触控 — 所有坐标为相对值 (0.0–1.0)
    def click(self, x: float, y: float) -> None: ...
    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5) -> None: ...
    def long_tap(self, x: float, y: float, duration: float = 1.0) -> None: ...

    # 按键 / 文本
    def key_event(self, key_code: int) -> None: ...
    def text(self, content: str) -> None: ...

    # 应用管理
    def start_app(self, package: str) -> None: ...
    def stop_app(self, package: str) -> None: ...
    def is_app_running(self, package: str) -> bool: ...

    # Shell
    def shell(self, cmd: str) -> str: ...


class ADBController(AndroidController):
    """基于 Airtest/ADB 的具体实现。

    - 内部坐标转换: px = int(x * width), py = int(y * height)
    - 截图: snapshot(quality=99) → RGB→BGR
    - 点击/滑动: 通过 `input tap/swipe` 命令
    - 截图超时: 可配置, 超时抛 EmulatorConnectionError
    """
```

### `autowsgr/emulator/os_control.py`

```python
class EmulatorProcessManager(ABC):
    """模拟器进程管理抽象基类 — 3 个抽象方法。"""
    def is_running(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def restart(self) -> None: ...              # 默认: stop + start
    def wait_until_online(self, timeout=120): ...  # 默认: 轮询 is_running


class WindowsEmulatorManager(EmulatorProcessManager):
    """雷电→ldconsole, MuMu→MuMuManager, 其他→taskkill"""

class MacEmulatorManager(EmulatorProcessManager):
    """pgrep/pkill + MuMu mumutool 支持"""

class LinuxEmulatorManager(EmulatorProcessManager):
    """支持 WSL (tasklist.exe/taskkill.exe) + 原生 Linux (pgrep/pkill)"""


def create_emulator_manager(config, os_type=None) -> EmulatorProcessManager:
    """工厂函数 — 自动检测 OS 并返回对应管理器。"""
```

### `autowsgr/emulator/__init__.py`

重导出所有公共 API：`AndroidController`, `ADBController`, `DeviceInfo`,
`EmulatorProcessManager`, `WindowsEmulatorManager`, `MacEmulatorManager`,
`LinuxEmulatorManager`, `create_emulator_manager`。

---

## 关键设计决策

| 决策 | 原方案 (文档) | 实际实现 | 原因 |
|------|--------------|---------|------|
| 坐标系统 | `int` 绝对坐标 | `float` 相对值 (0.0–1.0) | 与 Vision 层统一，无需关心分辨率 |
| 点击实现 | `device.touch()` | `input tap` shell 命令 | 与遗留系统一致，更可靠 |
| 滑动实现 | `device.swipe()` | `input swipe` shell 命令 | 同上 |
| long_tap | 未规划 | `swipe(x, y, x, y, duration)` | 遗留代码逻辑保留 |
| text 方法 | 未规划 | `device.text()` | 遗留代码有此功能 |
| shell 方法 | 未规划 | `device.shell()` | 遗留代码有此功能 |
| 工厂函数 | `classmethod` | 独立函数 `create_emulator_manager()` | 更 Pythonic |
| EmulatorProcessManager | `find_emulator()` 返回 Path | 路径来自 `EmulatorConfig` | 路径检测已在 `EmulatorType.auto_emulator_path()` 实现 |

---

## 与视觉层的关系

Emulator 层 **不依赖** Vision 层。截图返回原始 `np.ndarray`，由上层（UIControl）传给 Vision 层做识别。

```
UIControl 层:
    screen = emulator.screenshot()                    # Emulator
    result = checker.check(screen, signature)          # Vision
    if result.matched:
        emulator.click(result.detail[0].x, result.detail[0].y)  # Emulator (相对坐标)
```

这使得 AndroidController 可以独立测试，也可以替换为模拟实现。

---

## 测试覆盖 (72 tests)

| 测试文件 | 测试数 | 覆盖内容 |
|----------|--------|---------|
| `test_controller.py` | 40 | DeviceInfo 不可变性、ABC 约束、坐标转换 (5种分辨率)、截图 RGB→BGR、超时重试、按键/文本、应用管理、Shell、连接 mock |
| `test_os_control.py` | 32 | ABC 约束、restart 顺序、wait_until_online 超时、工厂函数 (3 OS)、Windows 各厂商检测、macOS pgrep、Linux ADB 设备列表、配置集成 |
