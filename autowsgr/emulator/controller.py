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

import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
from airtest.core.api import connect_device
from airtest.core.api import device as get_device
from airtest.core.error import AdbError, DeviceConnectionError

from autowsgr.infra import EmulatorConfig, EmulatorConnectionError
from autowsgr.infra.logger import caller_info, get_logger

from .detector import _find_adb, detect_emulators, prompt_user_select, resolve_serial


if TYPE_CHECKING:
    import numpy as np
    from airtest.core.android import Android


_log = get_logger('emulator')


# ── ADB 进程清理辅助 ──


def _kill_adb_process(adb_path: str | None = None) -> None:
    """终止已有的 adb 服务/进程，以便重新建立干净的连接。

    跨平台策略：

    1. 执行 ``adb kill-server``（ADB 官方方式，所有平台适用，优先）。
    2. Windows 下额外通过 ``taskkill /F /IM adb.exe`` 强制结束进程（兜底）。
    3. Unix 下额外通过 ``pkill -f adb`` 强制终止（兜底）。

    所有子步骤的失败均被静默忽略，不会向上抛出异常。
    """
    # Step 1: adb kill-server（跨平台正式方式）
    try:
        adb = adb_path or _find_adb()
        subprocess.run(
            [adb, 'kill-server'],
            timeout=5,
            capture_output=True,
        )
        _log.debug('[Emulator] adb kill-server 已执行')
    except Exception as exc:
        _log.debug('[Emulator] adb kill-server 失败: {}', exc)

    # Step 2: OS 级强制终止（兜底，防止 adb kill-server 本身挂起或找不到 adb）
    try:
        if sys.platform.startswith('win'):
            subprocess.run(
                ['taskkill', '/F', '/IM', 'adb.exe'],
                timeout=5,
                capture_output=True,
            )
            _log.debug('[Emulator] taskkill adb.exe 已执行')
        else:
            subprocess.run(
                ['pkill', '-f', 'adb'],
                timeout=5,
                capture_output=True,
            )
            _log.debug('[Emulator] pkill adb 已执行')
    except Exception as exc:
        _log.debug('[Emulator] OS 级终止 adb 进程失败: {}', exc)

    # Step 3: 重新启动 adb server，确保后续连接时 server 已就绪
    try:
        adb = adb_path or _find_adb()
        subprocess.run(
            [adb, 'start-server'],
            timeout=8,
            capture_output=True,
        )
        _log.debug('[Emulator] adb start-server 已执行')
    except Exception as exc:
        _log.debug('[Emulator] adb start-server 失败（连接时会自动启动）: {}', exc)


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
        config: EmulatorConfig | None = None,
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
                _log.info('[Emulator] 自动检测到唯一设备: {}', candidates[0].description)
            elif len(candidates) == 0:
                resolved = ''  # 交给 airtest "Android:///" 兜底
            else:
                resolved = prompt_user_select(candidates)
        self._serial = resolved or None

        # 使用 javacap 截图（minicap 在 Android 12+ x86_64 模拟器上不可用）
        uri = (
            f'Android:///{resolved}?cap_method=javacap'
            if resolved
            else 'Android:///?cap_method=javacap'
        )

        self._connect_with_retry(uri)
        assert self._device is not None  # _try_connect 成功后保证非 None

        # 获取分辨率
        display = self._device.display_info
        if not isinstance(display, dict):
            raise EmulatorConnectionError(
                f'display_info 返回非 dict 类型 {type(display).__name__}，serial={self._serial}'
            )
        width = display.get('width')
        height = display.get('height')
        if width is None or height is None:
            raise EmulatorConnectionError(
                f'无法获取设备分辨率: {self._serial}, display_info: {display}'
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
                orientation = getattr(self._device, '_current_orientation', None)
                if orientation == 1 and h_s > w_s:
                    w_s, h_s = h_s, w_s  # 旋转后的尺寸
                actual = (w_s, h_s)
                if actual != self._resolution:
                    _log.warning(
                        '[Emulator] display_info 分辨率 {}x{} 与实际截图 {}x{} 不符 '
                        '(设备可能处于横屏)，已修正',
                        *self._resolution,
                        w_s,
                        h_s,
                    )
                    self._resolution = actual
        except Exception as exc:
            _log.warning('[Emulator] 分辨率校验截图失败，使用 display_info 值: {}', exc)

        _log.info('[Emulator] 已连接设备: {} ({}x{})', self._serial or 'auto', *self._resolution)
        return DeviceInfo(
            serial=self._serial or 'auto',
            resolution=self._resolution,
        )

    # ── 内部连接辅助 ──

    def _try_connect(self, uri: str, *, kill_first: bool = False) -> None:
        """尝试建立设备连接（单次，不重试）。

        Parameters
        ----------
        uri:
            Airtest 设备 URI，如
            ``"Android:///127.0.0.1:16384?cap_method=javacap"``。
        kill_first:
            为 ``True`` 时先调用 :func:`_kill_adb_process` 清理残留的 adb
            进程再连接；首次尝试应传 ``False``，重试时传 ``True``。

        Raises
        ------
        EmulatorConnectionError
            连接失败时抛出。
        """
        if kill_first:
            _kill_adb_process()
        try:
            connect_device(uri)
            self._device = get_device()
        except (AdbError, DeviceConnectionError) as exc:
            raise EmulatorConnectionError(f'连接设备失败: {self._serial}') from exc

        if self._device is None:
            raise EmulatorConnectionError(f'连接后设备对象为 None: {self._serial}')

    def _connect_with_retry(
        self,
        uri: str,
        max_attempts: int = 3,
        retry_delay: float = 3.0,
    ) -> None:
        """带重试逻辑的连接入口，内部调用 :meth:`_try_connect`。

        策略：首次直接尝试连接（不 kill adb），失败后才执行清场再重试，
        避免在 adb 原本正常时无谓地破坏现有连接。

        Parameters
        ----------
        uri:
            Airtest 设备 URI。
        max_attempts:
            最大尝试次数（含首次），默认 3 次。
        retry_delay:
            相邻两次重试之间的等待秒数（含 adb start-server 预热时间），默认 3 秒。

        Raises
        ------
        EmulatorConnectionError
            所有重试均失败后抛出。
        """
        last_exc: EmulatorConnectionError | None = None
        for attempt in range(1, max_attempts + 1):
            # 首次直连；后续重试先 kill adb 再连（清场重连）
            kill_first = attempt > 1
            try:
                _log.info(
                    '[Emulator] 连接尝试 {}/{}{}: {}',
                    attempt,
                    max_attempts,
                    ' (kill-adb)' if kill_first else '',
                    uri,
                )
                self._try_connect(uri, kill_first=kill_first)
                return  # 连接成功，直接返回
            except EmulatorConnectionError as exc:
                last_exc = exc
                if attempt < max_attempts:
                    _log.warning(
                        '[Emulator] 连接失败 (尝试 {}/{}): {}，{:.1f}s 后重试...',
                        attempt,
                        max_attempts,
                        exc,
                        retry_delay,
                    )
                    time.sleep(retry_delay)

        raise EmulatorConnectionError(
            f'连接失败（共尝试 {max_attempts} 次）: {self._serial}'
        ) from last_exc

    def disconnect(self) -> None:
        serial = self._serial or 'auto'
        self._device = None
        self._resolution = (0, 0)
        _log.info('[Emulator] 已断开设备连接: {}', serial)

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    def _require_device(self) -> Android:
        """返回已连接的设备实例，未连接时抛出异常。"""
        if self._device is None:
            raise EmulatorConnectionError('设备未连接，请先调用 connect()')
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
                orientation = getattr(dev, '_current_orientation', None)
                if orientation == 1 and h > w:
                    rgb = cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)
                    h, w = rgb.shape[:2]

                elapsed = time.monotonic() - start
                # 运行时自动同步分辨率（防止旋转后首次使用仍是旧值）
                if self._resolution != (w, h):
                    _log.warning(
                        '[Emulator] 截图尺寸 {}x{} 与缓存分辨率 {}x{} 不符，已更新',
                        w,
                        h,
                        *self._resolution,
                    )
                    self._resolution = (w, h)
                _log.trace(
                    '[Emulator] 截图完成 {}x{} 耗时={:.3f}s',
                    w,
                    h,
                    elapsed,
                )
                return rgb
            if time.monotonic() - start > self._screenshot_timeout:
                raise EmulatorConnectionError(
                    f'截图超时 ({self._screenshot_timeout}s)，设备可能已失去响应'
                )
            time.sleep(0.1)

    # ── 触控 ──

    def click(self, x: float, y: float) -> None:
        dev = self._require_device()
        w, h = self._resolution
        px, py = int(x * w), int(y * h)
        _log.debug(
            '[Emulator] click({:.3f}, {:.3f}) → pixel({}, {})  res={}x{}  {}',
            x,
            y,
            px,
            py,
            w,
            h,
            caller_info(),
        )
        dev.shell(f'input tap {px} {py}')

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
        _log.debug(
            '[Emulator] swipe({:.3f},{:.3f}→{:.3f},{:.3f}) → pixel({},{}→{},{}) {}ms  {}',
            x1,
            y1,
            x2,
            y2,
            px1,
            py1,
            px2,
            py2,
            ms,
            caller_info(),
        )
        dev.shell(f'input swipe {px1} {py1} {px2} {py2} {ms}')

    def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
        self.swipe(x, y, x, y, duration=duration)

    # ── 按键 ──

    def key_event(self, key_code: int) -> None:
        dev = self._require_device()
        _log.debug('[Emulator] key_event({})  {}', key_code, caller_info())
        # airtest keyevent 内部调用 str.upper()，必须传字符串
        dev.keyevent(str(key_code))

    def text(self, content: str) -> None:
        dev = self._require_device()
        _log.debug("[Emulator] text('{}')  {}", content, caller_info())
        dev.text(content)

    # ── 应用管理 ──

    def start_app(self, package: str) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 启动应用: {}  {}', package, caller_info())
        dev.start_app(package)

    def stop_app(self, package: str) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 停止应用: {}  {}', package, caller_info())
        dev.stop_app(package)

    def is_app_running(self, package: str) -> bool:
        try:
            dev = self._require_device()
            ps_output = dev.shell('ps')
        except (AdbError, DeviceConnectionError, EmulatorConnectionError) as exc:
            _log.debug(
                "[Emulator] is_app_running('{}') → False (设备异常: {})  {}",
                package,
                exc,
                caller_info(),
            )
            return False
        if not isinstance(ps_output, str):
            _log.warning(
                "[Emulator] is_app_running: shell('ps') 返回非字符串 ({})，无法判断进程状态",
                type(ps_output).__name__,
            )
            return False
        running = package in ps_output
        _log.debug("[Emulator] is_app_running('{}') → {}  {}", package, running, caller_info())
        return running

    # ── Shell ──

    def shell(self, cmd: str) -> str:
        dev = self._require_device()
        result = dev.shell(cmd)
        if not isinstance(result, str):
            raise EmulatorConnectionError(
                f"shell('{cmd}') 返回了非字符串类型 {type(result).__name__}，airtest API 契约已变化"
            )
        return result
