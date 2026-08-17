"""出征准备页换船 e2e pytest 的共享 fixture 与命令行参数。

提供三个命令行参数:

- ``--config``: 用户配置文件路径 (YAML)，每次运行可加载不同配置
- ``--fleet``: 要更换的舰队编号 (1-4)
- ``--ships``: 目标舰船名列表，逗号分隔 (最多 6 个)

adb 校验在 :func:`game_ctx` fixture 中完成：adb 可执行文件不可用
或没有在线设备时，测试以 ``pytest.skip`` 跳过，不误报失败。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from autowsgr.emulator.detector import list_adb_devices
from autowsgr.infra import ConfigManager

if TYPE_CHECKING:
    from autowsgr.context import GameContext


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册换船 e2e 测试的命令行参数。"""
    group = parser.getgroup('change_fleet_e2e')
    group.addoption(
        '--config',
        default=None,
        help='用户配置文件路径 (YAML)；缺省时自动检测 usersettings.yaml',
    )
    group.addoption('--fleet', type=int, default=1, help='要更换的舰队编号 (1-4)')
    group.addoption(
        '--ships',
        default='U-47,U-96',
        help='目标舰船名列表，逗号分隔 (最多 6 个)',
    )


def _adb_ready() -> tuple[bool, str]:
    """校验 adb 可用性：可执行文件可用且至少有一台在线设备。"""
    try:
        devices = list_adb_devices()
    except Exception as exc:  # noqa: BLE001
        return False, f'adb 校验失败: {exc}'
    online = sorted(serial for serial, status in devices if status == 'device')
    if not online:
        return False, '未检测到在线设备 (adb devices 中无 device 状态)'
    return True, f'在线设备: {", ".join(online)}'


@pytest.fixture(scope='module')
def game_ctx(request: pytest.FixtureRequest) -> Iterator[GameContext]:
    """按指定 yaml 加载配置、连接模拟器并启动游戏；adb 未就绪时跳过测试。"""
    config_path: str | None = request.config.getoption('--config')
    ConfigManager.load(config_path)  # 提前校验 yaml 可正常加载

    ok, message = _adb_ready()
    if not ok:
        pytest.skip(message)

    from autowsgr.scheduler.launcher import launch

    ctx = launch(config_path)
    yield ctx
    ctx.ctrl.disconnect()


@pytest.fixture
def fleet_id(request: pytest.FixtureRequest) -> int:
    """目标舰队编号。"""
    return int(request.config.getoption('--fleet'))


@pytest.fixture
def ships(request: pytest.FixtureRequest) -> list[str | None]:
    """目标舰船名列表 (按槽位 0-5，缺省补 None)。"""
    raw: str = request.config.getoption('--ships')
    names = [name.strip() or None for name in raw.split(',')]
    return (names + [None] * 6)[:6]
