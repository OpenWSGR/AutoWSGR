"""Display selection and scrcpy lifecycle regressions without an Android device."""

from __future__ import annotations

import socket
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest
from pydantic import ValidationError

from autowsgr.emulator.controller.display import find_package_display
from autowsgr.emulator.controller.scrcpy import ScrcpyController
from autowsgr.infra import EmulatorConfig, EmulatorConnectionError


PACKAGE = 'com.huanmeng.zhanjian2'
StreamController = tuple[ScrcpyController, MagicMock, dict[str, int], list[list[str]]]


def activity_dump(display_id: int, package: str = PACKAGE) -> str:
    return (
        'ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n'
        f'Display #{display_id} (activities from top to bottom):\n'
        f'    mResumedActivity: ActivityRecord{{abc u0 {package}/.Game t3}}\n'
    )


@pytest.mark.parametrize('display_id', [0, 5, 6])
def test_find_resumed_display_including_zero(display_id: int):
    assert find_package_display(activity_dump(display_id), PACKAGE) == display_id


def test_resumed_activity_beats_stale_task_on_another_display():
    output = (
        '  Display #2 (activities from top to bottom):\n'
        f'    * Hist #0: ActivityRecord{{old u0 {PACKAGE}/.Game t1}}\n' + activity_dump(6)
    )
    assert find_package_display(output, PACKAGE) == 6


def test_falls_back_to_package_activity_before_it_is_resumed():
    output = (
        '  Display #5 (activities from top to bottom):\n'
        f'    * Hist #0: ActivityRecord{{new u0 {PACKAGE}/.Game t1}}\n'
    )
    assert find_package_display(output, PACKAGE) == 5


def test_stopped_game_last_paused_metadata_does_not_select_old_display():
    output = (
        'Display #6 (activities from top to bottom):\n'
        f'    mLastPausedActivity: ActivityRecord{{old u0 {PACKAGE}/.Login t-1 f}} isExiting}}\n'
        + activity_dump(0, 'app.lawnchair')
    )
    assert find_package_display(output, PACKAGE) is None


def test_live_mumu_history_record_can_select_game_before_resume():
    output = (
        'Display #6 (activities from top to bottom):\n'
        f'    * Hist  #0: ActivityRecord{{98425128 u0 {PACKAGE}/.Game t84}}\n'
    )
    assert find_package_display(output, PACKAGE) == 6


@pytest.mark.parametrize('other_package', [PACKAGE + '.other', 'other.' + PACKAGE])
def test_package_component_must_match_exactly(other_package: str):
    assert find_package_display(activity_dump(5, other_package), PACKAGE) is None


@pytest.mark.parametrize('header_indent', ['', '  '])
def test_global_resumed_summary_does_not_belong_to_last_display(header_indent: str):
    output = (
        activity_dump(0, 'app.lawnchair')
        + f'{header_indent}Display #6 (activities from top to bottom):\n'
        + '    mResumedActivity: null\n'
        + '\n'
        + f'  ResumedActivity: ActivityRecord{{global u0 {PACKAGE}/.Game t3}}\n'
    )
    assert find_package_display(output, PACKAGE) is None


def test_global_summary_cannot_override_display_activity_fallback():
    output = (
        'Display #5 (activities from top to bottom):\n'
        f'    * Hist #0: ActivityRecord{{a u0 {PACKAGE}/.Game t3}}\n'
        'Display #6 (activities from top to bottom):\n'
        '    mResumedActivity: null\n'
        f'  ResumedActivity: ActivityRecord{{global u0 {PACKAGE}/.Game t3}}\n'
    )
    assert find_package_display(output, PACKAGE) == 5


def test_mumu_display_task_area_resumed_list_excludes_global_summary():
    output = (
        'Display #6 (activities from top to bottom):\n'
        '  mResumedActivity: null\n'
        'Display #0 (activities from top to bottom):\n'
        '  Resumed activities in task display areas (from top to bottom):\n'
        '    Resumed: ActivityRecord{abc u0 app.lawnchair/.LawnchairLauncher t1}\n'
        '\n'
        f'  ResumedActivity: ActivityRecord{{global u0 {PACKAGE}/.Game t3}}\n'
        '\n'
        'ActivityTaskSupervisor state:\n'
    )
    assert find_package_display(output, PACKAGE) is None
    assert find_package_display(output, 'app.lawnchair') == 0


def test_manual_display_config_allows_zero_and_rejects_negative():
    assert EmulatorConfig().display_id is None
    assert EmulatorConfig(display_id=0).display_id == 0
    with pytest.raises(ValidationError):
        EmulatorConfig(display_id=-1)


@pytest.fixture
def stream_controller(monkeypatch: pytest.MonkeyPatch):
    """Exercise connection orchestration with an in-memory ADB and frame producer."""
    ctrl = ScrcpyController(serial='test', package_name=PACKAGE, screenshot_timeout=0.01)
    device = MagicMock()
    current = {'display': 0}
    servers: list[list[str]] = []

    def shell(command: str | list[str], **_kwargs: object) -> str | MagicMock:
        if command == ['pidof', PACKAGE]:
            return '123'
        if command == 'dumpsys activity activities':
            return activity_dump(current['display'])
        assert isinstance(command, list)
        servers.append(command)
        return MagicMock()

    device.shell.side_effect = shell
    device.create_connection.side_effect = lambda *_args: MagicMock(recv=lambda _size: b'\0')
    ctrl._device = device
    monkeypatch.setattr(ctrl, '_deploy_server', MagicMock())
    monkeypatch.setattr('autowsgr.emulator.controller.scrcpy.time.sleep', lambda _seconds: None)

    def produce_frame() -> None:
        ctrl._last_frame = np.full((3, 4, 3), ctrl.display_id, dtype=np.uint8)
        ctrl._resolution = (4, 3)
        ctrl._alive = True
        ctrl._frame_ready.set()

    monkeypatch.setattr(ctrl, '_start_decode_thread', produce_frame)
    ctrl._open_stream()
    yield ctrl, device, current, servers
    ctrl.disconnect()


def test_running_game_migration_rebuilds_video_and_control_together(
    stream_controller: StreamController,
):
    ctrl, device, current, servers = stream_controller
    previous_video = ctrl._video_socket
    previous_control = ctrl._control_socket
    current['display'] = 6
    ctrl._last_display_check = float('-inf')

    frame = ctrl.screenshot()

    assert ctrl.display_id == 6
    assert np.all(frame == 6)
    previous_video.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    previous_video.close.assert_called_once()
    previous_control.close.assert_called_once()
    assert 'display_id=6' in servers[-1]
    assert servers[0] != servers[-1]  # 新 session 使用独立 socket 名。
    video_call, control_call = device.create_connection.call_args_list[-2:]
    assert video_call.args[1] == control_call.args[1] == ctrl._socket_name
    ctrl.click(0.5, 0.5, delay=False)
    assert ctrl._control_socket.sendall.call_count == 2
    previous_control.sendall.assert_not_called()


def test_screenshot_display_queries_are_rate_limited(stream_controller: StreamController):
    ctrl, device, _current, _servers = stream_controller
    device.shell.reset_mock()
    for _ in range(10):
        ctrl.screenshot()
    device.shell.assert_not_called()
    ctrl._last_display_check = float('-inf')
    ctrl.screenshot()
    assert device.shell.call_args_list == [
        call(['pidof', PACKAGE]),
        call('dumpsys activity activities'),
    ]


def test_start_app_rechecks_display_immediately_after_cold_start(
    stream_controller: StreamController,
):
    ctrl, device, current, servers = stream_controller
    device.app_start.side_effect = lambda _package: current.update(display=5)
    ctrl.start_app(PACKAGE, delay=False)
    device.app_start.assert_called_once_with(PACKAGE)
    assert ctrl.display_id == 5
    assert 'display_id=5' in servers[-1]
    assert np.all(ctrl.screenshot() == 5)


def test_restart_closes_scrcpy_mirror_before_launching_app(stream_controller: StreamController):
    ctrl, device, current, servers = stream_controller
    current['display'] = 5
    ctrl._last_display_check = float('-inf')
    ctrl.screenshot()
    assert ctrl.display_id == 5
    previous_video = ctrl._video_socket
    previous_control = ctrl._control_socket
    previous_server = ctrl._server_stream
    connections_before_launch = device.create_connection.call_count
    shell = device.shell.side_effect
    state = {'running': False}

    def shell_after_stop(command: str | list[str], **kwargs: object) -> str | MagicMock:
        if command == ['pidof', PACKAGE]:
            return '123' if state['running'] else ''
        if command == 'dumpsys activity activities':
            if state['running']:
                return activity_dump(6)
            return activity_dump(5)  # force-stop 后仍残留的 Resumed 记录。
        return shell(command, **kwargs)

    def launch(_package: str) -> None:
        previous_video.close.assert_called_once()
        previous_control.close.assert_called_once()
        previous_server.close.assert_called_once()
        assert ctrl._video_socket is ctrl._control_socket is ctrl._server_stream is None
        assert not ctrl._alive
        assert device.create_connection.call_count == connections_before_launch
        state['running'] = True

    device.shell.side_effect = shell_after_stop
    device.app_start.side_effect = launch
    ctrl.stop_app(PACKAGE, delay=False)
    ctrl.start_app(PACKAGE, delay=False)
    assert 'display_id=5' in servers[-2]
    assert 'display_id=6' in servers[-1]
    assert np.all(ctrl.screenshot() == 6)


def test_app_launch_failure_leaves_old_mirror_closed(stream_controller: StreamController):
    ctrl, device, _current, _servers = stream_controller
    previous_video = ctrl._video_socket
    device.app_start.side_effect = RuntimeError('cannot launch')
    with pytest.raises(RuntimeError, match='cannot launch'):
        ctrl.start_app(PACKAGE, delay=False)
    previous_video.close.assert_called_once()
    assert ctrl._video_socket is ctrl._control_socket is ctrl._server_stream is None
    assert not ctrl._alive


def test_broken_stream_rechecks_display_even_within_poll_interval(
    stream_controller: StreamController,
):
    ctrl, _device, current, servers = stream_controller
    current['display'] = 6
    ctrl._alive = False
    assert np.all(ctrl.screenshot() == 6)
    assert ctrl.display_id == 6
    assert 'display_id=6' in servers[-1]


def test_manual_display_zero_overrides_package_detection():
    ctrl = ScrcpyController(config=EmulatorConfig(display_id=0), package_name=PACKAGE)
    ctrl._device = MagicMock()
    ctrl._device.shell.return_value = activity_dump(6)
    ctrl._display_id = 5
    assert ctrl._resolve_display_id() == 0
    ctrl._device.shell.assert_not_called()


def test_missing_activity_returns_default_but_failed_detection_preserves_current_display():
    ctrl = ScrcpyController(package_name=PACKAGE)
    ctrl._display_id = 5
    ctrl._device = MagicMock()
    ctrl._device.shell.side_effect = lambda command: (
        '123' if command == ['pidof', PACKAGE] else activity_dump(0, 'app.lawnchair')
    )
    assert ctrl._resolve_display_id() == 0
    ctrl._device.shell.side_effect = OSError('device busy')
    assert ctrl._resolve_display_id() == 5


def test_no_process_ignores_stale_resumed_display_and_rebuilds_default(
    stream_controller: StreamController,
):
    ctrl, device, current, servers = stream_controller
    current['display'] = 5
    ctrl._last_display_check = float('-inf')
    ctrl.screenshot()
    original_shell = device.shell.side_effect

    def shell(command: str | list[str], **kwargs: object) -> str | MagicMock:
        if command == ['pidof', PACKAGE]:
            return ''
        return original_shell(command, **kwargs)

    device.shell.side_effect = shell
    device.shell.reset_mock()
    ctrl._alive = False
    ctrl.screenshot()
    assert ctrl.display_id == 0
    assert 'display_id=0' in servers[-1]
    assert call('dumpsys activity activities') not in device.shell.call_args_list


@pytest.mark.parametrize('pid_output', ['/system/bin/sh: pidof: not found', 'device offline'])
def test_invalid_process_query_preserves_current_display(pid_output: str):
    ctrl = ScrcpyController(package_name=PACKAGE)
    ctrl._display_id = 5
    ctrl._device = MagicMock()
    ctrl._device.shell.return_value = pid_output
    assert ctrl._resolve_display_id() == 5


def test_detected_new_display_survives_transient_dump_failure_during_rebuild(
    stream_controller: StreamController,
):
    ctrl, device, _current, servers = stream_controller
    shell = device.shell.side_effect
    responses = iter([activity_dump(6), OSError('transient ADB failure')])

    def transient_shell(command: str | list[str], **kwargs: object) -> str | MagicMock:
        if command == 'dumpsys activity activities':
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        return shell(command, **kwargs)

    device.shell.side_effect = transient_shell
    ctrl._last_display_check = float('-inf')
    ctrl.screenshot()
    assert ctrl.display_id == 6
    assert 'display_id=6' in servers[-1]


@pytest.mark.parametrize('failure', ['control', 'first_frame'])
def test_failed_open_closes_partial_resources(monkeypatch: pytest.MonkeyPatch, failure: str):
    ctrl = ScrcpyController(screenshot_timeout=0)
    video, control, server = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(ctrl, '_deploy_server', lambda: None)
    monkeypatch.setattr(ctrl, '_start_server', lambda: setattr(ctrl, '_server_stream', server))
    monkeypatch.setattr(
        ctrl, '_connect_video_socket', lambda: setattr(ctrl, '_video_socket', video)
    )

    def connect_control() -> None:
        ctrl._control_socket = control
        if failure == 'control':
            raise EmulatorConnectionError('control failure')

    monkeypatch.setattr(ctrl, '_connect_control_socket', connect_control)
    monkeypatch.setattr(ctrl, '_start_decode_thread', lambda: setattr(ctrl, '_alive', True))
    with pytest.raises(EmulatorConnectionError):
        ctrl._open_stream()
    video.close.assert_called_once()
    control.close.assert_called_once()
    server.close.assert_called_once()
    assert not ctrl._alive
    assert ctrl._video_socket is ctrl._control_socket is ctrl._server_stream is None
    assert not ctrl._frame_ready.is_set()


def test_disconnect_stops_worker_blocked_on_socket_read(monkeypatch: pytest.MonkeyPatch):
    # 真正的 socketpair 覆盖 close() 单独调用无法可靠唤醒 recv() 的情况。
    codec = SimpleNamespace(parse=lambda _raw: [])
    fake_av = SimpleNamespace(CodecContext=SimpleNamespace(create=lambda *_args: codec))
    monkeypatch.setitem(sys.modules, 'av', fake_av)
    ctrl = ScrcpyController()
    reader, writer = socket.socketpair()
    try:
        ctrl._video_socket = reader
        ctrl._start_decode_thread()
        worker = ctrl._decode_thread
        ctrl.disconnect()
        assert not worker.is_alive()
        assert ctrl._decode_stop.is_set()
        assert ctrl._decode_thread is None
        assert ctrl._video_socket is None
        assert not ctrl._alive
    finally:
        reader.close()
        writer.close()


def test_stale_decoder_cannot_publish_frames_or_clear_new_stream(monkeypatch: pytest.MonkeyPatch):
    stale_stop = threading.Event()
    new_frame = np.ones((3, 4, 3), dtype=np.uint8)
    stale_frame = SimpleNamespace(to_ndarray=lambda **_kwargs: np.zeros_like(new_frame))

    def decode(_packet: object) -> list[SimpleNamespace]:
        stale_stop.set()  # 关闭发生在解码中，帧提交前。
        return [stale_frame]

    codec = SimpleNamespace(parse=lambda _raw: [object()], decode=decode)
    fake_av = SimpleNamespace(CodecContext=SimpleNamespace(create=lambda *_args: codec))
    monkeypatch.setitem(sys.modules, 'av', fake_av)
    ctrl = ScrcpyController()
    ctrl._alive = True
    ctrl._last_frame = new_frame
    ctrl._decode_stop = threading.Event()  # 模拟已启动的新一代 worker。
    ctrl._stream_loop(MagicMock(recv=lambda _size: b'video'), stale_stop)
    assert ctrl._alive
    assert ctrl._last_frame is new_frame


@pytest.mark.parametrize('gesture', ['touch', 'scroll'])
def test_input_retry_recomputes_coordinates_after_reconnect(
    monkeypatch: pytest.MonkeyPatch, gesture: str
):
    ctrl = ScrcpyController()
    ctrl._alive = True
    ctrl._resolution = (960, 540)
    failed_socket = MagicMock()
    failed_socket.sendall.side_effect = BrokenPipeError('display disappeared')
    new_socket = MagicMock()
    ctrl._control_socket = failed_socket
    dimensions = []
    original_conversion = ctrl._to_absolute

    def convert(x: float, y: float) -> tuple[int, int]:
        dimensions.append(ctrl.resolution)
        return original_conversion(x, y)

    def reconnect() -> None:
        ctrl._resolution = (1920, 1080)
        ctrl._control_socket = new_socket
        ctrl._alive = True

    monkeypatch.setattr(ctrl, '_to_absolute', convert)
    monkeypatch.setattr(ctrl, '_reopen_stream', reconnect)
    if gesture == 'touch':
        ctrl._inject_touch(0, 0.5, 0.5)
    else:
        ctrl._inject_scroll(0.5, 0.5, horizontal=0, vertical=1)

    assert dimensions == [(960, 540), (1920, 1080)]
    failed_socket.sendall.assert_called_once()
    new_socket.sendall.assert_called_once()
    assert failed_socket.sendall.call_args != new_socket.sendall.call_args
