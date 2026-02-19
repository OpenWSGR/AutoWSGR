# 模拟器操作层 (Emulator)

## 职责

提供 **纯粹的设备控制**：连接、截图、点击、滑动、键入。

**不做**任何图像匹配、页面识别或游戏逻辑判断。

---

## 现状问题

当前 `AndroidController` (~470 行) 混杂了：
- 设备操作：`click()`, `swipe()`, `update_screen()`, `get_screen()`
- 图像匹配：`image_exist()`, `wait_image()`, `wait_images()`, `click_image()`
- 像素检查：`check_pixel()`, `get_pixel()`

其中 `wait_images()` 返回值语义极为混乱：
```python
# 现状：找到返回 0-based index，超时返回 None 或 -1，取决于调用方式
if ret := self.wait_images([img1, img2], timeout=5):  # type: int | None
    # ret == 0 时被视为 False！
```

---

## 新设计

```python
# autowsgr/emulator/controller.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
from loguru import logger


@dataclass(frozen=True)
class DeviceInfo:
    """设备信息"""
    serial: str
    resolution: tuple[int, int]   # (width, height)
    name: str = ""


class AndroidController(ABC):
    """Android 设备控制器抽象基类
    
    仅负责设备操作，不做任何图像识别。
    """
    
    @abstractmethod
    def connect(self) -> DeviceInfo:
        """连接设备，返回设备信息"""
        ...
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        ...
    
    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """截图，返回 BGR 格式的 numpy 数组"""
        ...
    
    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """点击指定坐标"""
        ...
    
    @abstractmethod
    def swipe(
        self, 
        x1: int, y1: int, 
        x2: int, y2: int, 
        duration: float = 0.5,
    ) -> None:
        """滑动"""
        ...
    
    @abstractmethod
    def key_event(self, key_code: int) -> None:
        """发送按键事件"""
        ...
    
    @abstractmethod
    def start_app(self, package: str, activity: str = "") -> None:
        """启动应用"""
        ...
    
    @abstractmethod
    def stop_app(self, package: str) -> None:
        """停止应用"""
        ...
    
    @abstractmethod
    def is_app_running(self, package: str) -> bool:
        """检查应用是否在运行"""
        ...
    
    @property
    @abstractmethod
    def resolution(self) -> tuple[int, int]:
        """设备分辨率"""
        ...


class ADBController(AndroidController):
    """基于 ADB (airtest) 的设备控制器"""
    
    def __init__(self, serial: str | None = None) -> None:
        self._serial = serial
        self._device = None
        self._resolution: tuple[int, int] = (960, 540)
    
    def connect(self) -> DeviceInfo:
        from airtest.core.api import connect_device, device as get_device
        
        uri = f"android:///{self._serial}" if self._serial else "android:///"
        connect_device(uri)
        self._device = get_device()
        
        # 获取分辨率
        display = self._device.display_info
        self._resolution = (display["width"], display["height"])
        
        logger.info("已连接设备: {} ({}x{})", self._serial, *self._resolution)
        return DeviceInfo(
            serial=self._serial or "auto",
            resolution=self._resolution,
        )
    
    def disconnect(self) -> None:
        self._device = None
        logger.info("已断开设备")
    
    def screenshot(self) -> np.ndarray:
        """截图（BGR 格式）"""
        import cv2
        screen = self._device.snapshot(quality=99)  # RGB ndarray
        return cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    
    def click(self, x: int, y: int) -> None:
        logger.trace("click({}, {})", x, y)
        self._device.touch((x, y))
    
    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5
    ) -> None:
        logger.trace("swipe({},{} → {},{})", x1, y1, x2, y2)
        self._device.swipe((x1, y1), (x2, y2), duration=duration)
    
    def key_event(self, key_code: int) -> None:
        self._device.keyevent(key_code)
    
    def start_app(self, package: str, activity: str = "") -> None:
        self._device.start_app(package, activity or None)
    
    def stop_app(self, package: str) -> None:
        self._device.stop_app(package)
    
    def is_app_running(self, package: str) -> bool:
        # 通过检查前台应用判断
        return package in (self._device.get_top_activity_name() or "")
    
    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution
```

---

## OS 层控制器

模拟器进程管理（启动/关闭/检测）不属于 Android 设备控制，单独设计：

```python
# autowsgr/emulator/os_control.py

from abc import ABC, abstractmethod
from pathlib import Path
from loguru import logger


class EmulatorProcessManager(ABC):
    """模拟器进程管理（操作系统级）"""
    
    @abstractmethod
    def find_emulator(self) -> Path | None:
        """自动检测模拟器安装路径"""
        ...
    
    @abstractmethod
    def start_emulator(self, path: Path) -> str:
        """启动模拟器，返回 ADB serial"""
        ...
    
    @abstractmethod
    def stop_emulator(self) -> None:
        """关闭模拟器"""
        ...
    
    @abstractmethod
    def is_emulator_running(self) -> bool:
        """检查模拟器是否在运行"""
        ...
    
    @classmethod
    def create(cls, os_type: str, emulator_type: str) -> "EmulatorProcessManager":
        """工厂方法"""
        import platform
        os_name = platform.system()
        if os_name == "Windows":
            return WindowsEmulatorManager(emulator_type)
        elif os_name == "Darwin":
            return MacEmulatorManager(emulator_type)
        elif os_name == "Linux":
            return LinuxEmulatorManager(emulator_type)
        raise ValueError(f"不支持的操作系统: {os_name}")


class WindowsEmulatorManager(EmulatorProcessManager):
    """Windows 下的模拟器管理"""
    
    def __init__(self, emulator_type: str) -> None:
        self._type = emulator_type
    
    def find_emulator(self) -> Path | None:
        """从注册表自动检测"""
        import winreg
        registry_paths = {
            "雷电": r"SOFTWARE\leidian\ldplayer9",
            "蓝叠": r"SOFTWARE\BlueStacks_nxt",
            "MuMu": r"SOFTWARE\MuMu",
        }
        reg_path = registry_paths.get(self._type)
        if not reg_path:
            return None
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
            return Path(install_dir)
        except OSError:
            return None
    
    def start_emulator(self, path: Path) -> str:
        import subprocess
        subprocess.Popen([str(path)])
        # ... 等待 ADB 端口可用
        return "127.0.0.1:5555"
    
    def stop_emulator(self) -> None:
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "dnplayer.exe"], capture_output=True)
    
    def is_emulator_running(self) -> bool:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq dnplayer.exe"],
            capture_output=True, text=True,
        )
        return "dnplayer.exe" in result.stdout


# MacEmulatorManager, LinuxEmulatorManager 类似
```

---

## 与视觉层的关系

Emulator 层 **不依赖** Vision 层。截图返回原始 `np.ndarray`，由上层（UIControl）传给 Vision 层做识别。

```
UIControl 层:
    screen = emulator.screenshot()              # Emulator
    result = matcher.match(screen, template)     # Vision
    if result:
        emulator.click(result.position[0], ...)  # Emulator
```

这使得 AndroidController 可以独立测试，也可以替换为模拟实现（用于单元测试）。
