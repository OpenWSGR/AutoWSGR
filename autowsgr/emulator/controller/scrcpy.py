"""scrcpy 设备控制器 — 基于 adbutils + scrcpy-server 的实现。

通过 scrcpy 协议获取 H264 视频流并解码为截图；触控（click/swipe/long_tap）、
按键和文本输入通过 scrcpy 控制流（INJECT_TOUCH_EVENT / INJECT_KEYCODE /
INJECT_TEXT）实现，延迟远低于 ``adb shell input``。仅应用启停、运行检测等
非实时操作仍走 ADB。

使用方式::

    from autowsgr.emulator.controller import ScrcpyController

    ctrl = ScrcpyController(serial="emulator-5554")
    info = ctrl.connect()
    screen = ctrl.screenshot()
    ctrl.click(0.5, 0.5)
    ctrl.disconnect()
"""

from __future__ import annotations

import random
import socket
import struct
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.infra import EmulatorConfig, EmulatorConnectionError
from autowsgr.infra.config import OPERATION_DELAY_MAX, OPERATION_DELAY_MIN
from autowsgr.infra.logger import caller_info, get_logger

from ..detector import _find_adb, detect_emulators, prompt_user_select, resolve_serial
from .protocol import AndroidController, DeviceInfo


if TYPE_CHECKING:
    import numpy as np
    from adbutils import AdbConnection, AdbDevice

_log = get_logger('emulator')

# scrcpy-server.jar 打包在 autowsgr/data/bin/ 下
_SCRCPY_SERVER_JAR = Path(__file__).resolve().parents[2] / 'data' / 'bin' / 'scrcpy-server.jar'
_SCRCPY_SERVER_VERSION = '2.7'
_DEVICE_JAR_PATH = '/data/local/tmp/scrcpy-server.jar'

# ── scrcpy 2.7 控制流协议常量 ──
# 参考：scrcpy app/src/control_msg.h / control_msg.c (v2.7)

# 控制消息类型
_TYPE_INJECT_KEYCODE = 0
_TYPE_INJECT_TEXT = 1
_TYPE_INJECT_TOUCH_EVENT = 2
_TYPE_INJECT_SCROLL_EVENT = 3
_TYPE_SET_CLIPBOARD = 9

# SET_CLIPBOARD 文本上限（SC_CONTROL_MSG_CLIPBOARD_TEXT_MAX_LENGTH = 1<<18 - 14）
_CLIPBOARD_TEXT_MAX_LENGTH = (1 << 18) - 14

# Android MotionEvent 动作码
_ACTION_DOWN = 0
_ACTION_UP = 1
_ACTION_MOVE = 2

# Android KeyEvent 动作码
_KEY_ACTION_DOWN = 0
_KEY_ACTION_UP = 1

# Pointer id（触摸用）
# scrcpy 中 SC_POINTER_ID_GENERIC_FINGER = UINT64_C(-2)，
# 作为有符号 int64 写入 q 格式即 -2，对应无符号 0xFFFFFFFFFFFFFFFE
_POINTER_ID_FINGER = -2


class ScrcpyController(AndroidController):
    """基于 scrcpy 协议的 Android 设备控制器。

    截图通过 scrcpy-server 提供的 H264 视频流解码获得（30+ fps）；
    触控（click/swipe/long_tap）、按键与文本输入通过 scrcpy 控制流实现，
    相比 ``adb shell input`` 显著降低延迟。仅应用管理类操作仍走 ADB。

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
        self._control_socket: socket.socket | None = None
        self._decode_thread: threading.Thread | None = None
        self._frame_ready = threading.Event()  # 首帧就绪信号
        self._frame_lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._control_lock = threading.Lock()  # 控制流写串行化

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
        self._connect_control_socket()
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

        def _try_connect() -> None:
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

        max_attempts = 3
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    _log.info('[Emulator] 重试连接 ({}/{})...', attempt, max_attempts)
                    self._restart_adb_server()
                    time.sleep(2.0)

                _try_connect()
            except Exception as exc:
                last_exc = exc
                _log.warning('[Emulator] 连接失败 (尝试 {}/{}): {}', attempt, max_attempts, exc)
            else:
                return

        raise EmulatorConnectionError(
            f'连接设备失败（共尝试 {max_attempts} 次）: {self._serial}'
        ) from last_exc

    def _restart_adb_server(self) -> None:
        """重启 adb server。"""
        import subprocess

        try:
            adb = _find_adb()
            subprocess.run([adb, 'kill-server'], timeout=5, capture_output=True, check=False)  # noqa: S603
            time.sleep(1)
            subprocess.run([adb, 'start-server'], timeout=8, capture_output=True, check=False)  # noqa: S603
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
            'control=true',
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

    def _connect_control_socket(self) -> None:
        """连接 scrcpy 控制通道（video 之后建立的第二个 socket）。

        scrcpy 2.7 中 ``send_dummy_byte=true`` 时 dummy byte 仅由第一个 socket
        （video）发送，控制 socket 无需读取 dummy byte。
        """
        import adbutils

        dev = self._require_device()
        for _attempt in range(30):
            try:
                self._control_socket = dev.create_connection(
                    adbutils.Network.LOCAL_ABSTRACT,
                    'scrcpy',
                )
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise EmulatorConnectionError('无法连接 scrcpy-server 控制通道（3s 超时）')

        # 禁用 Nagle，降低控制指令延迟
        try:
            self._control_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        _log.debug('[Emulator] scrcpy 控制通道已连接')

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
        if self._control_socket is not None:
            try:
                self._control_socket.close()
            except Exception as exc:
                _log.debug('[Scrcpy] 关闭 control socket 失败: {}', exc)
            self._control_socket = None

        if self._video_socket is not None:
            try:
                self._video_socket.close()
            except Exception as exc:
                _log.debug('[Scrcpy] 关闭 video socket 失败: {}', exc)
            self._video_socket = None

        if self._server_stream is not None:
            try:
                self._server_stream.close()
            except Exception as exc:
                _log.debug('[Scrcpy] 关闭 server stream 失败: {}', exc)
            self._server_stream = None

        if self._decode_thread is not None:
            self._decode_thread.join(timeout=3.0)
            self._decode_thread = None

        self._alive = False
        self._frame_ready.clear()

    def _reopen_stream(self) -> None:
        """在保持 ADB 设备连接的前提下重建 scrcpy 视频流与控制流。"""
        self._close_video_channel()
        self._last_frame = None
        self._deploy_server()
        self._start_server()
        self._connect_video_socket()
        self._connect_control_socket()
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

    # ── 控制流消息发送 ──

    def _require_control_socket(self) -> socket.socket:
        """返回控制 socket；视频流未就绪时先尝试恢复。"""
        self._ensure_stream_alive()
        if self._control_socket is None:
            raise EmulatorConnectionError('scrcpy 控制通道未连接')
        return self._control_socket

    def _send_control(self, data: bytes) -> None:
        """向控制 socket 串行写入一帧消息（线程安全）。"""
        sock = self._require_control_socket()
        with self._control_lock:
            try:
                sock.sendall(data)
            except (ConnectionError, OSError) as exc:
                _log.warning('[Emulator] 控制流发送失败，触发重连: {}', exc)
                self._alive = False
                self._ensure_stream_alive()
                sock = self._require_control_socket()
                sock.sendall(data)
            time.sleep(0.05)  # 避免连续发送过快导致游戏处理不及

    @staticmethod
    def _float_to_u16fp(value: float) -> int:
        """将 [0.0, 1.0] 压力值编码为 scrcpy u16 定点数。"""
        clamped = max(0.0, min(1.0, value))
        return round(clamped * 0xFFFF)

    def _to_absolute(self, x: float, y: float) -> tuple[int, int]:
        """将相对坐标 [0.0, 1.0] 转换为设备像素坐标。"""
        w, h = self._resolution
        return int(x * w), int(y * h)

    def _inject_touch(
        self,
        action: int,
        x: float,
        y: float,
        pressure: float = 1.0,
        pointer_id: int = _POINTER_ID_FINGER,
    ) -> None:
        """发送 INJECT_TOUCH_EVENT 控制消息（scrcpy 2.7，32 字节）。

        布局：type(1) | action(1) | pointer_id(8) | x(4) | y(4)
              | width(2) | height(2) | pressure(2) | action_button(4) | buttons(4)
        """
        w, h = self._resolution
        px, py = self._to_absolute(x, y)
        u16_pressure = self._float_to_u16fp(pressure)
        data = struct.pack(
            '>BBqIIHHHII',
            _TYPE_INJECT_TOUCH_EVENT,
            action,
            pointer_id,
            px,
            py,
            w,
            h,
            u16_pressure,
            0,  # action_button（触摸事件为 0）
            0,  # buttons（触摸事件为 0）
        )
        # struct '>BBqIIHHHII' = 1+1+8+4+4+2+2+2+4+4 = 32 字节
        self._send_control(data)

    def _inject_keycode(self, key_code: int, action: int = _KEY_ACTION_UP) -> None:
        """发送 INJECT_KEYCODE 控制消息（scrcpy 2.7，14 字节）。

        布局：type(1) | action(1) | keycode(4) | repeat(4) | metastate(4)
        """
        data = struct.pack(
            '>BBIII',
            _TYPE_INJECT_KEYCODE,
            action,
            key_code,
            0,  # repeat
            0,  # metastate
        )
        self._send_control(data)

    def _inject_text(self, content: str) -> None:
        """发送 INJECT_TEXT 控制消息（scrcpy 2.7）。

        布局：type(1) | length(4) | utf8_bytes
        最大长度 300 字节。

        注意：INJECT_TEXT 通过 InputConnection.commitText 注入，
        仅对 ASCII/拉丁字符可靠；中文等多字节字符请使用 :meth:`_set_clipboard`。
        """
        raw = content.encode('utf-8')[:300]
        data = struct.pack('>BI', _TYPE_INJECT_TEXT, len(raw)) + raw
        self._send_control(data)

    def _set_clipboard(self, content: str, paste: bool = True) -> None:
        """发送 SET_CLIPBOARD 控制消息（scrcpy 2.7）。

        布局：type(1) | sequence(8) | paste(1) | length(4) | utf8_bytes

        ``paste=True`` 时，server 在设置剪贴板后会自动注入
        ``KEYCODE_PASTE``（Android ≥ 7），实现立即粘贴。
        该路径通过系统剪贴板 + 粘贴键工作，可正确输入中文等
        INJECT_TEXT 无法处理的字符。

        Parameters
        ----------
        content:
            要输入的文本（UTF-8，最长 262130 字节）。
        paste:
            是否在设置剪贴板后立即粘贴。
        """
        raw = content.encode('utf-8')[:_CLIPBOARD_TEXT_MAX_LENGTH]
        # sequence=0 表示 SEQUENCE_INVALID，不请求 ack
        data = struct.pack('>BQBI', _TYPE_SET_CLIPBOARD, 0, 1 if paste else 0, len(raw)) + raw
        self._send_control(data)

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
    # 引入一个开关，当参数为：click(x, y, delay=False) 时关闭延迟，该方法默认打开全局延迟，全局延迟可以在 config.py 内设置
    def click(self, x: float, y: float, *, delay: bool = True) -> None:
        w, h = self._resolution
        px, py = self._to_absolute(x, y)
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
        self._inject_touch(_ACTION_DOWN, x, y, pressure=1.0)
        self._inject_touch(_ACTION_UP, x, y, pressure=0.0)

        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration: float = 0.5,
        *,
        delay: bool = True,
    ) -> None:
        px1, py1 = self._to_absolute(x1, y1)
        px2, py2 = self._to_absolute(x2, y2)
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
        # 按下
        self._inject_touch(_ACTION_DOWN, x1, y1, pressure=1.0)
        # 在 duration 内插值若干 MOVE 事件，保证流畅滑动
        steps = max(1, ms // 16)  # ~60fps，每步约 16ms
        step_ms = ms / steps
        for i in range(1, steps + 1):
            t = i / steps
            cx = x1 + (x2 - x1) * t
            cy = y1 + (y2 - y1) * t
            self._inject_touch(_ACTION_MOVE, cx, cy, pressure=1.0)
            time.sleep(step_ms / 1000.0)
        # 抬起
        self._inject_touch(_ACTION_UP, x2, y2, pressure=0.0)

        # 增加延迟，改动同 click_delay
        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

    def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
        px, py = self._to_absolute(x, y)
        ms = int(duration * 1000)
        _log.debug(
            '[Emulator] long_tap({:.3f}, {:.3f}) → pixel({},{}) {}ms  {}',
            x,
            y,
            px,
            py,
            ms,
            caller_info(),
        )
        # 按下后保持不动，再抬起（与 input swipe 同点等价）
        self._inject_touch(_ACTION_DOWN, x, y, pressure=1.0)
        time.sleep(duration)
        self._inject_touch(_ACTION_UP, x, y, pressure=0.0)

    # ── 按键 ──
    def key_event(self, key_code: int, *, delay: bool = True) -> None:
        _log.debug('[Emulator] key_event({})  {}', key_code, caller_info())
        # 发送 DOWN + UP 完成一次按键
        self._inject_keycode(key_code, action=_KEY_ACTION_DOWN)
        self._inject_keycode(key_code, action=_KEY_ACTION_UP)

        # 增加延迟，改动同 click_delay
        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

    def text(self, content: str, *, delay: bool = True) -> None:
        _log.debug("[Emulator] text('{}')  {}", content, caller_info())
        if content.isascii():
            # 纯 ASCII/拉丁字符走 INJECT_TEXT（延迟更低）
            self._inject_text(content)
        else:
            # 含中文等多字节字符 → SET_CLIPBOARD + paste（Android ≥ 7）
            self._set_clipboard(content, paste=True)

        # 增加延迟，改动同 click_delay
        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

    # ── 应用管理 ──

    def start_app(self, package: str, *, delay: bool = True) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 启动应用: {}  {}', package, caller_info())
        dev.app_start(package)

        # 增加延迟，改动同 click_delay
        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

    def stop_app(self, package: str, *, delay: bool = True) -> None:
        dev = self._require_device()
        _log.info('[Emulator] 停止应用: {}  {}', package, caller_info())
        dev.app_stop(package)

        # 增加延迟，改动同 click_delay
        if delay:  # True 才走延迟
            time.sleep(
                random.uniform(
                    min(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                    max(OPERATION_DELAY_MIN, OPERATION_DELAY_MAX),
                )
            )

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
