"""测试 autowsgr.emulator.detector。"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from autowsgr.emulator.detector import (
    EmulatorCandidate,
    _find_adb,
    connect_and_list_devices,
    detect_emulators,
    identify_emulator_type,
    list_adb_devices,
    prompt_user_select,
    resolve_serial,
)
from autowsgr.infra import EmulatorConfig, EmulatorConnectionError
from autowsgr.types import EmulatorType


class TestIdentifyEmulatorType:
    """模拟器类型识别测试。"""

    @pytest.mark.parametrize(
        ('serial', 'expected'),
        [
            ('emulator-5554', EmulatorType.leidian),
            ('emulator-5556', EmulatorType.leidian),
            ('127.0.0.1:16384', EmulatorType.mumu),
            ('127.0.0.1:16416', EmulatorType.mumu),
            ('127.0.0.1:62001', EmulatorType.mumu),
            ('127.0.0.1:5555', EmulatorType.bluestacks),
            ('127.0.0.1:5565', EmulatorType.bluestacks),
            ('unknown-device', None),
            ('', None),
        ],
    )
    def test_identify(self, serial: str, expected: EmulatorType | None) -> None:
        assert identify_emulator_type(serial) == expected


class TestEmulatorCandidate:
    """EmulatorCandidate 数据类测试。"""

    def test_description_known(self) -> None:
        cand = EmulatorCandidate(
            serial='emulator-5554',
            emulator_type=EmulatorType.leidian,
            status='device',
        )
        assert '雷电' in cand.description
        assert 'emulator-5554' in cand.description
        assert 'device' in cand.description

    def test_description_unknown(self) -> None:
        cand = EmulatorCandidate(
            serial='foo',
            emulator_type=None,
            status='offline',
        )
        assert '未知' in cand.description


class TestListAdbDevices:
    """adb devices 输出解析测试。"""

    def test_parse_two_devices(self) -> None:
        output = 'List of devices attached\nemulator-5554\tdevice\n127.0.0.1:16384\toffline\n'
        with patch(
            'autowsgr.emulator.detector.subprocess.run',
            return_value=MagicMock(stdout=output),
        ):
            devices = list_adb_devices(adb_path='/fake/adb')
        assert devices == [('emulator-5554', 'device'), ('127.0.0.1:16384', 'offline')]

    def test_parse_empty(self) -> None:
        output = 'List of devices attached\n'
        with patch(
            'autowsgr.emulator.detector.subprocess.run',
            return_value=MagicMock(stdout=output),
        ):
            devices = list_adb_devices(adb_path='/fake/adb')
        assert devices == []

    def test_timeout(self) -> None:
        from subprocess import TimeoutExpired

        with (
            patch(
                'autowsgr.emulator.detector.subprocess.run',
                side_effect=TimeoutExpired('adb devices', 10),
            ),
            pytest.raises(EmulatorConnectionError, match='超时'),
        ):
            list_adb_devices(adb_path='/fake/adb')


class TestDetectEmulators:
    """设备探测过滤测试。"""

    def test_filter_offline(self) -> None:
        raw = [
            ('emulator-5554', 'device'),
            ('127.0.0.1:16384', 'offline'),
        ]
        with patch(
            'autowsgr.emulator.detector.list_adb_devices',
            return_value=raw,
        ):
            candidates = detect_emulators()
        assert len(candidates) == 1
        assert candidates[0].serial == 'emulator-5554'

    def test_sorted(self) -> None:
        raw = [
            ('emulator-5556', 'device'),
            ('emulator-5554', 'device'),
        ]
        with patch(
            'autowsgr.emulator.detector.list_adb_devices',
            return_value=raw,
        ):
            candidates = detect_emulators()
        assert [c.serial for c in candidates] == ['emulator-5554', 'emulator-5556']


class TestFindAdb:
    """adb 路径查找测试。"""

    def test_shutil_which_found(self) -> None:
        with patch('autowsgr.emulator.detector.shutil.which', return_value='/usr/bin/adb'):
            assert _find_adb() == '/usr/bin/adb'

    def test_shutil_which_not_found_raises(self) -> None:
        with (
            patch('autowsgr.emulator.detector.shutil.which', return_value=None),
            patch('autowsgr.emulator.detector.sys.platform', 'linux'),
            pytest.raises(FileNotFoundError),
        ):
            _find_adb()


class TestResolveSerial:
    """resolve_serial 决策逻辑测试。"""

    def test_priority_1_config_serial(self) -> None:
        config = EmulatorConfig(serial='my-serial')
        assert resolve_serial(config) == 'my-serial'

    def test_priority_2_single_device(self) -> None:
        config = EmulatorConfig(serial='')
        with patch(
            'autowsgr.emulator.detector.detect_emulators',
            return_value=[
                EmulatorCandidate(
                    serial='emulator-5554',
                    emulator_type=EmulatorType.leidian,
                    status='device',
                ),
            ],
        ):
            assert resolve_serial(config) == 'emulator-5554'

    def test_priority_5_no_devices(self) -> None:
        config = EmulatorConfig(serial='')
        with (
            patch(
                'autowsgr.emulator.detector.detect_emulators',
                return_value=[],
            ),
            pytest.raises(EmulatorConnectionError, match='未检测到'),
        ):
            resolve_serial(config)

    def test_priority_3_type_match_single(self) -> None:
        config = EmulatorConfig(serial='', type=EmulatorType.leidian)
        with patch(
            'autowsgr.emulator.detector.detect_emulators',
            return_value=[
                EmulatorCandidate(
                    serial='emulator-5554',
                    emulator_type=EmulatorType.leidian,
                    status='device',
                ),
                EmulatorCandidate(
                    serial='127.0.0.1:16384',
                    emulator_type=EmulatorType.mumu,
                    status='device',
                ),
            ],
        ):
            assert resolve_serial(config) == 'emulator-5554'

    def test_priority_3_type_match_multiple_prompt(self) -> None:
        config = EmulatorConfig(serial='', type=EmulatorType.leidian)
        with (
            patch(
                'autowsgr.emulator.detector.detect_emulators',
                return_value=[
                    EmulatorCandidate(
                        serial='emulator-5554',
                        emulator_type=EmulatorType.leidian,
                        status='device',
                    ),
                    EmulatorCandidate(
                        serial='emulator-5556',
                        emulator_type=EmulatorType.leidian,
                        status='device',
                    ),
                ],
            ),
            patch('autowsgr.emulator.detector.sys.stdin.isatty', return_value=False),
            pytest.raises(EmulatorConnectionError, match='无法自动选择'),
        ):
            resolve_serial(config)

    def test_priority_4_multiple_prompt_tty(self) -> None:
        config = EmulatorConfig(serial='')
        with (
            patch(
                'autowsgr.emulator.detector.detect_emulators',
                return_value=[
                    EmulatorCandidate(
                        serial='emulator-5554',
                        emulator_type=EmulatorType.leidian,
                        status='device',
                    ),
                    EmulatorCandidate(
                        serial='127.0.0.1:16384',
                        emulator_type=EmulatorType.mumu,
                        status='device',
                    ),
                ],
            ),
            patch('autowsgr.emulator.detector.sys.stdin.isatty', return_value=True),
            patch(
                'autowsgr.emulator.detector.input',
                return_value='0',
            ),
        ):
            assert resolve_serial(config) == 'emulator-5554'


class TestPromptUserSelect:
    """用户交互选择测试。"""

    def test_non_tty_raises(self) -> None:
        candidates = [
            EmulatorCandidate('a', None, 'device'),
            EmulatorCandidate('b', None, 'device'),
        ]
        with (
            patch.object(sys.stdin, 'isatty', return_value=False),
            pytest.raises(
                EmulatorConnectionError,
                match='无法自动选择',
            ),
        ):
            prompt_user_select(candidates)

    def test_tty_valid_input(self) -> None:
        candidates = [
            EmulatorCandidate('a', EmulatorType.leidian, 'device'),
            EmulatorCandidate('b', EmulatorType.mumu, 'device'),
        ]
        with (
            patch.object(sys.stdin, 'isatty', return_value=True),
            patch(
                'autowsgr.emulator.detector.input',
                return_value='1',
            ),
        ):
            assert prompt_user_select(candidates) == 'b'

    def test_tty_invalid_then_valid(self) -> None:
        candidates = [
            EmulatorCandidate('a', None, 'device'),
        ]
        with (
            patch.object(sys.stdin, 'isatty', return_value=True),
            patch(
                'autowsgr.emulator.detector.input',
                side_effect=['abc', '0'],
            ),
        ):
            assert prompt_user_select(candidates) == 'a'


class TestConnectAndListDevices:
    """adb connect + list 测试。"""

    def test_connect_then_list(self) -> None:
        with (
            patch(
                'autowsgr.emulator.detector._find_adb',
                return_value='/fake/adb',
            ),
            patch(
                'autowsgr.emulator.detector.subprocess.run',
                return_value=MagicMock(stdout='', stderr=''),
            ) as mock_run,
            patch(
                'autowsgr.emulator.detector.list_adb_devices',
                return_value=[('127.0.0.1:16384', 'device')],
            ) as mock_list,
        ):
            result = connect_and_list_devices()
            assert result == [('127.0.0.1:16384', 'device')]
            assert mock_run.call_count == 2  # connect x2 + list x0 (mocked)
            mock_list.assert_called_once_with('/fake/adb')
