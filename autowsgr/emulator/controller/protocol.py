"""Android 设备控制器协议 — 抽象基类与数据类型。

定义设备控制器的公共接口，所有具体实现（ADB、Minitouch 等）
均须实现 :class:`AndroidController` 中声明的抽象方法。

所有触控坐标使用 **相对值** (0.0-1.0)：

- 左上角 = (0.0, 0.0)
- 右下角趋近 (1.0, 1.0)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """已连接设备的基本信息。

    Attributes
    ----------
    serial:
        ADB serial 地址。
    resolution:
        设备屏幕分辨率 ``(width, height)``。
    """

    serial: str
    resolution: tuple[int, int]


class AndroidController(ABC):
    """Android 设备控制器抽象基类。

    仅负责设备操作，不做任何图像识别。
    子类实现具体连接方式（ADB / Minitouch 等）。
    """

    # ── 连接管理 ──

    @abstractmethod
    def connect(self) -> DeviceInfo:
        """连接设备，返回设备信息。

        Raises
        ------
        EmulatorConnectionError
            连接失败时抛出。
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开设备连接。"""
        ...

    @property
    @abstractmethod
    def resolution(self) -> tuple[int, int]:
        """设备屏幕分辨率 ``(width, height)``。"""
        ...

    # ── 截图 ──

    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """截取当前屏幕，返回 RGB uint8 数组 ``(H, W, 3)``。

        Raises
        ------
        EmulatorConnectionError
            截图超时或设备无响应。
        """
        ...

    # ── 触控 ──

    @abstractmethod
    def click(self, x: float, y: float, *, delay: bool = True) -> None:
        """点击屏幕。

        Parameters
        ----------
        x, y:
            相对坐标 (0.0-1.0)。
        delay:
            是否在点击后等待操作延迟（默认 True）。
        """
        ...

    @abstractmethod
    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration: float = 0.5,
    ) -> None:
        """滑动。

        Parameters
        ----------
        x1, y1:
            起始相对坐标。
        x2, y2:
            终止相对坐标。
        duration:
            滑动持续时间（秒）。
        """
        ...

    @abstractmethod
    def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
        """长按。

        Parameters
        ----------
        x, y:
            相对坐标。
        duration:
            按住时间（秒）。
        """
        ...

    # ── 按键 ──

    @abstractmethod
    def key_event(self, key_code: int) -> None:
        """发送 Android KeyEvent。

        Parameters
        ----------
        key_code:
            Android KeyEvent 键值（如 3 = HOME, 4 = BACK）。
        """
        ...

    @abstractmethod
    def text(self, content: str) -> None:
        """输入文本。

        Parameters
        ----------
        content:
            要输入的文本。
        """
        ...

    # ── 应用管理 ──

    @abstractmethod
    def start_app(self, package: str) -> None:
        """启动 Android 应用。

        Parameters
        ----------
        package:
            应用包名。
        """
        ...

    @abstractmethod
    def stop_app(self, package: str) -> None:
        """停止 Android 应用。"""
        ...

    @abstractmethod
    def is_app_running(self, package: str) -> bool:
        """检查应用是否在前台运行。"""
        ...

    # ── Shell ──

    @abstractmethod
    def shell(self, cmd: str) -> str:
        """执行 ADB shell 命令并返回 stdout。"""
        ...
