"""Android 设备控制器 — 模拟器层核心。

提供纯粹的设备操作能力（截图、点击、滑动、按键、应用管理），
**不做**任何图像识别、页面判定或游戏逻辑。

所有触控坐标使用 **相对值** (0.0–1.0)：

- 左上角 = (0.0, 0.0)
- 右下角趋近 (1.0, 1.0)
- 内部自动根据实际分辨率转换为像素坐标

使用方式::

    from autowsgr.emulator.controller import ADBController

    ctrl = ADBController(serial="emulator-5554")
    info = ctrl.connect()
    screen = ctrl.screenshot()
    ctrl.click(0.5, 0.5)
    ctrl.disconnect()
"""

from __future__ import annotations

import inspect
import time
import cv2
from abc import ABC, abstractmethod
from dataclasses import dataclass
from .detector import detect_emulators, prompt_user_select, resolve_serial

import numpy as np
from loguru import logger
from autowsgr.infra import EmulatorConfig, EmulatorConnectionError
from airtest.core.api import connect_device
from airtest.core.api import device as get_device
from airtest.core.error import AdbError, DeviceConnectionError
from airtest.core.android import Android

# ── 日志开关（由 infra.logger.setup_logger 写入）──────────────────────────────
_show_screenshot_detail: bool = False


def _caller_info(depth: int = 2) -> str:
    """返回调用栈中指定深度的调用者信息（文件名:行号 in 函数名）。

    depth=2 表示跳过 _caller_info 本身与直接调用它的函数，指向再上一层的调用者。
    """
    try:
        frame = inspect.stack()[depth]
        filename = frame.filename.replace("\\", "/").rsplit("/", 1)[-1]
        return f"{filename}:{frame.lineno} in {frame.function}"
    except Exception:
        return "<unknown>"


def configure(*, show_screenshot_detail: bool = False) -> None:
    """配置 controller 模块的日志行为。

    Parameters
    ----------
    show_screenshot_detail:
        ``True`` 时输出每次截图的完成日志（尺寸/耗时）；
        ``False``（默认）时静默该日志，避免刷屏。
    """
    global _show_screenshot_detail
    _show_screenshot_detail = show_screenshot_detail


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
    def click(self, x: float, y: float) -> None:
        """点击屏幕。

        Parameters
        ----------
        x, y:
            相对坐标 (0.0–1.0)。
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


# ── ADB 实现 ──


class ADBController(AndroidController):
    """基于 Airtest / ADB 的 Android 设备控制器。

    Parameters
    ----------
    serial:
        设备的 ADB serial 地址（如 ``"emulator-5554"``、``"127.0.0.1:16384"``）。
        为 None 时自动检测；若同时提供了 ``config``，则走完整的
        :func:`~autowsgr.emulator.detector.resolve_serial` 决策流程。
    config:
        :class:`~autowsgr.infra.config.EmulatorConfig` 实例，用于辅助多设备时的
        自动筛选。``serial`` 非空时此参数被忽略。
    screenshot_timeout:
        截图超时（秒），超过后抛出异常。
    """

    def __init__(
        self,
        serial: str | None = None,
        config: "EmulatorConfig | None" = None,
        screenshot_timeout: float = 10.0,
    ) -> None:
        self._serial = serial
        self._config = config
        self._screenshot_timeout = screenshot_timeout
        self._device: Android | None = None  # airtest.core.android.Android
        self._resolution: tuple[int, int] = (0, 0)

    # ── 连接 ──

    def connect(self) -> DeviceInfo:
        # ── serial 解析 ──
        # 优先使用构造时传入的 serial；否则走自动检测流程。
        if self._serial:
            resolved = self._serial
        elif self._config is not None:
            resolved = resolve_serial(self._config)
        else:
            # 无配置时，尝试纯 adb devices 自动检测（单设备场景）
            candidates = detect_emulators()
            if len(candidates) == 1:
                resolved = candidates[0].serial
                logger.info("[Emulator] 自动检测到唯一设备: {}", candidates[0].description)
            elif len(candidates) == 0:
                resolved = ""  # 交给 airtest "Android:///" 兜底
            else:
                resolved = prompt_user_select(candidates)
        self._serial = resolved or None

        # 使用 javacap 截图（minicap 在 Android 12+ x86_64 模拟器上不可用）
        uri = (
            f"Android:///{resolved}?cap_method=javacap"
            if resolved
            else "Android:///?cap_method=javacap"
        )


        try:
            connect_device(uri)
            self._device = get_device()
        except (AdbError, DeviceConnectionError) as exc:
            raise EmulatorConnectionError(f"连接设备失败: {self._serial}") from exc

        if self._device is None:
            raise EmulatorConnectionError(f"连接后设备对象为 None: {self._serial}")

        # 获取分辨率
        display = self._device.display_info
        if not isinstance(display, dict):
            raise EmulatorConnectionError(
                f"display_info 返回非 dict 类型 {type(display).__name__}，"
                f"serial={self._serial}"
            )
        width = display.get("width")
        height = display.get("height")
        if width is None or height is None:
            raise EmulatorConnectionError(
                f"无法获取设备分辨率: {self._serial}, display_info: {display}"
            )
        self._resolution = (int(width), int(height))

        # ── 用首张截图校正分辨率（display_info 不考虑旋转方向） ──
        # 当设备处于横屏时 display_info 仍返回物理竖屏尺寸，
        # 实际截图尺寸才反映真实坐标系，必须以此为准。
        try:
            raw = self._device.snapshot(quality=99)
            if raw is not None:
                h_s, w_s = raw.shape[:2]
                # javacap 在横屏设备上返回竖屏截图，需顺时针旋转 90°
                orientation = getattr(self._device, "_current_orientation", None)
                if orientation == 1 and h_s > w_s:
                    w_s, h_s = h_s, w_s  # 旋转后的尺寸
                actual = (w_s, h_s)
                if actual != self._resolution:
                    logger.warning(
                        "[Emulator] display_info 分辨率 {}x{} 与实际截图 {}x{} 不符 "
                        "(设备可能处于横屏)，已修正",
                        *self._resolution, w_s, h_s,
                    )
                    self._resolution = actual
        except Exception as exc:
            logger.warning("[Emulator] 分辨率校验截图失败，使用 display_info 值: {}", exc)

        logger.info(
            "[Emulator] 已连接设备: {} ({}x{})", self._serial or "auto", *self._resolution
        )
        return DeviceInfo(
            serial=self._serial or "auto",
            resolution=self._resolution,
        )

    def disconnect(self) -> None:
        serial = self._serial or "auto"
        self._device = None
        self._resolution = (0, 0)
        logger.info("[Emulator] 已断开设备连接: {}", serial)

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    def _require_device(self) -> Android:
        """返回已连接的设备实例，未连接时抛出异常。"""
        if self._device is None:
            raise EmulatorConnectionError("设备未连接，请先调用 connect()")
        return self._device

    # ── 截图 ──

    def screenshot(self) -> np.ndarray:
        dev = self._require_device()
        start = time.monotonic()
        while True:
            screen = dev.snapshot(quality=99)  # airtest 返回 BGR ndarray
            if screen is not None:
                rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)

                # javacap 在横屏设备上返回未旋转的竖屏截图，
                # 需要顺时针旋转 90° 使其与显示坐标系一致。
                h, w = rgb.shape[:2]
                orientation = getattr(dev, "_current_orientation", None)
                if orientation == 1 and h > w:
                    rgb = cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)
                    h, w = rgb.shape[:2]

                elapsed = time.monotonic() - start
                # 运行时自动同步分辨率（防止旋转后首次使用仍是旧值）
                if self._resolution != (w, h):
                    logger.warning(
                        "[Emulator] 截图尺寸 {}x{} 与缓存分辨率 {}x{} 不符，已更新",
                        w, h, *self._resolution,
                    )
                    self._resolution = (w, h)
                if _show_screenshot_detail:
                    logger.debug(
                        "[Emulator] 截图完成 {}x{} 耗时={:.3f}s",
                        w, h, elapsed,
                    )
                return rgb
            if time.monotonic() - start > self._screenshot_timeout:
                raise EmulatorConnectionError(
                    f"截图超时 ({self._screenshot_timeout}s)，设备可能已失去响应"
                )
            time.sleep(0.1)

    # ── 触控 ──

    def click(self, x: float, y: float) -> None:
        dev = self._require_device()
        w, h = self._resolution
        px, py = int(x * w), int(y * h)
        logger.debug("[Emulator] click({:.3f}, {:.3f}) → pixel({}, {})  res={}x{}  caller={}", x, y, px, py, w, h, _caller_info())
        dev.shell(f"input tap {px} {py}")

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration: float = 0.5,
    ) -> None:
        w, h = self._resolution
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        ms = int(duration * 1000)
        dev = self._require_device()
        logger.debug(
            "[Emulator] swipe({:.3f},{:.3f}→{:.3f},{:.3f}) → pixel({},{}→{},{}) {}ms  caller={}",
            x1, y1, x2, y2, px1, py1, px2, py2, ms, _caller_info(),
        )
        dev.shell(f"input swipe {px1} {py1} {px2} {py2} {ms}")

    def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
        self.swipe(x, y, x, y, duration=duration)

    # ── 按键 ──

    def key_event(self, key_code: int) -> None:
        dev = self._require_device()
        logger.debug("[Emulator] key_event({})  caller={}", key_code, _caller_info())
        # airtest keyevent 内部调用 str.upper()，必须传字符串
        dev.keyevent(str(key_code))

    def text(self, content: str) -> None:
        dev = self._require_device()
        logger.debug("[Emulator] text('{}')  caller={}", content, _caller_info())
        dev.text(content)

    # ── 应用管理 ──

    def start_app(self, package: str) -> None:
        dev = self._require_device()
        logger.info("[Emulator] 启动应用: {}  caller={}", package, _caller_info())
        dev.start_app(package)

    def stop_app(self, package: str) -> None:
        dev = self._require_device()
        logger.info("[Emulator] 停止应用: {}  caller={}", package, _caller_info())
        dev.stop_app(package)

    def is_app_running(self, package: str) -> bool:
        try:
            dev = self._require_device()
            ps_output = dev.shell("ps")
        except (AdbError, DeviceConnectionError, EmulatorConnectionError) as exc:
            logger.debug("[Emulator] is_app_running('{}') → False (设备异常: {})  caller={}", package, exc, _caller_info())
            return False
        if not isinstance(ps_output, str):
            logger.warning(
                "[Emulator] is_app_running: shell('ps') 返回非字符串 ({})，无法判断进程状态",
                type(ps_output).__name__,
            )
            return False
        running = package in ps_output
        logger.debug("[Emulator] is_app_running('{}') → {}  caller={}", package, running, _caller_info())
        return running

    # ── Shell ──

    def shell(self, cmd: str) -> str:
        dev = self._require_device()
        result = dev.shell(cmd)
        if not isinstance(result, str):
            raise EmulatorConnectionError(
                f"shell('{cmd}') 返回了非字符串类型 {type(result).__name__}，"
                "airtest API 契约已变化"
            )
        return result
