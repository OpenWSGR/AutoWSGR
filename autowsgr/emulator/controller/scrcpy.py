"""scrcpy 设备控制器 — 基于 adbutils + scrcpy-server 的实现。

通过 scrcpy 协议获取 H264 视频流并解码为截图，使用 adbutils 执行
ADB 命令实现触控/按键等操作。

使用方式::

    from autowsgr.emulator.controller import ScrcpyController

    ctrl = ScrcpyController(serial="emulator-5554")
    info = ctrl.connect()
    screen = ctrl.screenshot()
    ctrl.click(0.5, 0.5)
    ctrl.disconnect()
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.infra import EmulatorConfig, EmulatorConnectionError
from autowsgr.infra.logger import caller_info, get_logger

from ..detector import _find_adb, detect_emulators, prompt_user_select, resolve_serial
from .protocol import AndroidController, DeviceInfo


if TYPE_CHECKING:
    import socket

    import numpy as np
    from adbutils import AdbConnection, AdbDevice

_log = get_logger('emulator')

# scrcpy-server.jar 打包在 autowsgr/data/bin/ 下
_SCRCPY_SERVER_JAR = Path(__file__).resolve().parents[2] / 'data' / 'bin' / 'scrcpy-server.jar'
_SCRCPY_SERVER_VERSION = '2.7'
_DEVICE_JAR_PATH = '/data/local/tmp/scrcpy-server.jar'


class ScrcpyController(AndroidController):
    """基于 scrcpy 协议的 Android 设备控制器。

    截图通过 scrcpy-server 提供的 H264 视频流解码获得（30+ fps），
    触控/按键等操作通过 adbutils 的 ``adb shell input`` 实现。

    Parameters
    ----------
    serial:
        设备的 ADB serial 地址（如 ``"emulator-5554"``、``"127.0.0.1:16384"``）。
        为 None 时自动检测。
    config:
        :class:`~autowsgr.infra.config.EmulatorConfig` 实例。
    max_size:
        视频流最大尺寸（宽或高的上限，0 = 不限制）。
    bitrate:
        视频流码率（bps），默认 8Mbps。
    max_fps:
        视频流最大帧率（0 = 不限制）。
    screenshot_timeout:
        截图超时（秒），超过仍无帧时抛出异常。
    """

    def __init__(
        self,
        serial: str | None = None,
        config: EmulatorConfig | None = None,
        max_size: int = 0,
        bitrate: int = 8_000_000,
        max_fps: int = 0,
        screenshot_timeout: float = 10.0,
    ) -> None:
        self._serial = serial
        self._config = config
        self._max_size = max_size
        self._bitrate = bitrate
        self._max_fps = max_fps
        self._screenshot_timeout = screenshot_timeout

        self._device: AdbDevice | None = None
        self._resolution: tuple[int, int] = (0, 0)
        self._last_frame: np.ndarray | None = None

        # scrcpy 连接状态
        self._alive = False
        self._server_stream: AdbConnection | None = None
        self._video_socket: socket.socket | None = None
        self._decode_thread: threading.Thread | None = None
        self._frame_ready = threading.Event()  # 首帧就绪信号
        self._frame_lock = threading.Lock()
        self._reconnect_lock = threading.Lock()

    # ── 连接 ──

    def connect(self) -> DeviceInfo:

        # ── serial 解析 ──
        if self._serial:
            resolved = self._serial
        elif self._config is not None:
            resolved = resolve_serial(self._config)
        else:
            candidates = detect_emulators()
            if len(candidates) == 1:
                resolved = candidates[0].serial
                _log.info('[Emulator] 自动检测到唯一设备: {}', candidates[0].description)
            elif len(candidates) == 0:
                resolved = ''
            else:
                resolved = prompt_user_select(candidates)
        self._serial = resolved or None

        # ── 连接 adbutils 设备 ──
        self._connect_adb_device(resolved)
        assert self._device is not None

        # ── 获取初始分辨率 ──
        wsize = self._device.window_size()
        if wsize:
            self._resolution = (wsize[0], wsize[1])
        else:
            self._resolution = (960, 540)  # fallback
            _log.warning('[Emulator] 无法获取设备分辨率，使用默认值 960x540')

        # ── 部署并启动 scrcpy-server ──
        self._deploy_server()
        self._start_server()
        self._connect_video_socket()
        self._start_decode_thread()

        # ── 等待首帧 ──
        if not self._frame_ready.wait(timeout=self._screenshot_timeout):
            raise EmulatorConnectionError(
                f'scrcpy 视频流未能在 {self._screenshot_timeout}s 内产生首帧'
            )

        _log.info(
            '[Emulator] 已连接设备 (scrcpy): {} ({}x{})',
            self._serial or 'auto',
            *self._resolution,
        )
        return DeviceInfo(
            serial=self._serial or 'auto',
            resolution=self._resolution,
        )

    def _connect_adb_device(self, serial: str | None) -> None:
        """通过 adbutils 连接设备。"""
        import adbutils

        max_attempts = 3
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    _log.info('[Emulator] 重试连接 ({}/{})...', attempt, max_attempts)
                    self._restart_adb_server()
                    time.sleep(2.0)

                if serial:
                    # TCP 地址（如 127.0.0.1:16384）需先 adb connect
                    if ':' in serial:
                        adbutils.adb.connect(serial, timeout=5.0)
                    self._device = adbutils.adb.device(serial=serial)
                else:
                    devices = adbutils.adb.device_list()
                    if not devices:
                        raise EmulatorConnectionError('未发现已连接的 ADB 设备')
                    self._device = devices[0]
                    self._serial = self._device.serial
                return
            except Exception as exc:
                last_exc = exc
                _log.warning('[Emulator] 连接失败 (尝试 {}/{}): {}', attempt, max_attempts, exc)

        raise EmulatorConnectionError(
            f'连接设备失败（共尝试 {max_attempts} 次）: {self._serial}'
        ) from last_exc

    def _restart_adb_server(self) -> None:
        """重启 adb server。"""
        import subprocess

        try:
            adb = _find_adb()
            subprocess.run([adb, 'kill-server'], timeout=5, capture_output=True)
            time.sleep(1)
            subprocess.run([adb, 'start-server'], timeout=8, capture_output=True)
        except Exception as exc:
            _log.debug('[Emulator] 重启 adb server 失败: {}', exc)

    def _deploy_server(self) -> None:
        """推送 scrcpy-server.jar 到设备。"""
        if not _SCRCPY_SERVER_JAR.exists():
            raise EmulatorConnectionError(
                f'找不到 scrcpy-server.jar: {_SCRCPY_SERVER_JAR}\n请确认 autowsgr 包数据完整'
            )
        _log.debug('[Emulator] 推送 scrcpy-server.jar 到设备...')
        dev = self._require_device()
        dev.push(str(_SCRCPY_SERVER_JAR), _DEVICE_JAR_PATH)

    def _start_server(self) -> None:
        """在设备上启动 scrcpy-server 进程。"""
        cmd = [
            f'CLASSPATH={_DEVICE_JAR_PATH}',
            'app_process',
            '/',
            'com.genymobile.scrcpy.Server',
            _SCRCPY_SERVER_VERSION,
            'log_level=info',
            'tunnel_forward=true',
            'video=true',
            'audio=false',
            'control=false',
            f'max_size={self._max_size}',
            f'video_bit_rate={self._bitrate}',
            f'max_fps={self._max_fps}',
            'video_codec=h264',
            'send_device_meta=false',
            'send_frame_meta=false',
            'send_codec_meta=false',
            'send_dummy_byte=true',
        ]
        _log.debug('[Emulator] 启动 scrcpy-server: {}', ' '.join(cmd))
        dev = self._require_device()
        self._server_stream = dev.shell(cmd, stream=True)
        # 给 server 一点启动时间
        time.sleep(0.5)

    def _connect_video_socket(self) -> None:
        """连接 scrcpy 视频 socket。"""
        import adbutils

        dev = self._require_device()
        for _attempt in range(30):
            try:
                self._video_socket = dev.create_connection(
                    adbutils.Network.LOCAL_ABSTRACT,
                    'scrcpy',
                )
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise EmulatorConnectionError('无法连接 scrcpy-server 视频通道（3s 超时）')

        # 读取 dummy byte
        dummy = self._video_socket.recv(1)
        if not dummy:
            raise EmulatorConnectionError('未收到 scrcpy dummy byte，连接可能已断开')
        _log.debug('[Emulator] scrcpy 视频通道已连接')

    def _start_decode_thread(self) -> None:
        """启动后台 H264 解码线程。"""
        self._alive = True
        self._decode_thread = threading.Thread(
            target=self._stream_loop,
            name='scrcpy-decode',
            daemon=True,
        )
        self._decode_thread.start()

    def _stream_loop(self) -> None:
        """后台解码循环：接收 H264 流并解码为 numpy 帧。"""
        import av

        codec = av.CodecContext.create('h264', 'r')
        video_sock = self._video_socket
        assert video_sock is not None
        while self._alive:
            try:
                raw = video_sock.recv(0x10000)
                if not raw:
                    if self._alive:
                        _log.warning('[Emulator] scrcpy 视频流已断开')
                        self._alive = False
                    break

                for packet in codec.parse(raw):
                    for frame in codec.decode(packet):
                        rgb = frame.to_ndarray(format='rgb24')
                        h, w = rgb.shape[:2]

                        with self._frame_lock:
                            self._last_frame = rgb
                            if self._resolution != (w, h):
                                _log.info(
                                    '[Emulator] scrcpy 视频分辨率: {}x{}',
                                    w,
                                    h,
                                )
                                self._resolution = (w, h)

                        if not self._frame_ready.is_set():
                            self._frame_ready.set()

            except BlockingIOError:
                time.sleep(0.01)
            except (ConnectionError, OSError) as exc:
                if self._alive:
                    _log.warning('[Emulator] scrcpy 视频流异常: {}', exc)
                    self._alive = False
                break

    def disconnect(self) -> None:
        serial = self._serial or 'auto'
        self._close_video_channel()

        self._device = None
        self._resolution = (0, 0)
        self._last_frame = None
        _log.info('[Emulator] 已断开设备连接: {}', serial)

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    def _require_device(self) -> AdbDevice:
        """返回已连接的设备实例，未连接时抛出异常。"""
        if self._device is None:
            raise EmulatorConnectionError('设备未连接，请先调用 connect()')
        return self._device

    def _close_video_channel(self) -> None:
        if self._video_socket is not None:
            try:
                self._video_socket.close()
            except Exception:
                pass
            self._video_socket = None

        if self._server_stream is not None:
            try:
                self._server_stream.close()
            except Exception:
                pass
            self._server_stream = None

        if self._decode_thread is not None:
            self._decode_thread.join(timeout=3.0)
            self._decode_thread = None

        self._alive = False
        self._frame_ready.clear()

    def _reopen_stream(self) -> None:
        """在保持 ADB 设备连接的前提下重建 scrcpy 视频流。"""
        self._close_video_channel()
        self._last_frame = None
        self._deploy_server()
        self._start_server()
        self._connect_video_socket()
        self._start_decode_thread()

        if not self._frame_ready.wait(timeout=self._screenshot_timeout):
            raise EmulatorConnectionError(
                f'scrcpy 视频流重连失败：{self._screenshot_timeout}s 内无首帧'
            )

        _log.info('[Emulator] scrcpy 视频流已重连')

    def _ensure_stream_alive(self) -> None:
        """确保视频流可用，不可用时尝试一次重连。"""
        if self._alive:
            return

        with self._reconnect_lock:
            if self._alive:
                return

            _log.warning('[Emulator] 检测到视频流未运行，尝试自动重连')
            self._reopen_stream()

    # ── 截图 ──

    def screenshot(self) -> np.ndarray:

        self._ensure_stream_alive()

        start = time.monotonic()
        while True:
            with self._frame_lock:
                frame = self._last_frame

            if frame is not None:
                elapsed = time.monotonic() - start
                h, w = frame.shape[:2]
                _log.trace(
                    '[Emulator] 截图完成 {}x{} 耗时={:.3f}s',
                    w,
                    h,
                    elapsed,
                )
                return frame

            if not self._alive:
                self._ensure_stream_alive()
                start = time.monotonic()
                continue

            if time.monotonic() - start > self._screenshot_timeout:
                raise EmulatorConnectionError(
                    f'截图超时 ({self._screenshot_timeout}s)，scrcpy 视频流无数据'
                )
            time.sleep(0.01)

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
        dev = self._require_device()
        w, h = self._resolution
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        ms = int(duration * 1000)
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
        dev.keyevent(key_code)

    def text(self, content: str) -> None:
        dev = self._require_device()
        _log.debug("[Emulator] text('{}')  {}", content, caller_info())
        dev.send_keys(content)

    # ── 应用管理 ──

    def start_app(self, package: str) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 启动应用: {}  {}', package, caller_info())
        dev.app_start(package)

    def stop_app(self, package: str) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 停止应用: {}  {}', package, caller_info())
        dev.app_stop(package)

    def is_app_running(self, package: str) -> bool:
        try:
            dev = self._require_device()
            ps_output = dev.shell('ps -A')
        except Exception as exc:
            _log.debug(
                "[Emulator] is_app_running('{}') → False (设备异常: {})  {}",
                package,
                exc,
                caller_info(),
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
            return str(result)
        return result
