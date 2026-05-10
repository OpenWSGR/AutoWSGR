"""Tests for autowsgr.emulator.controller.protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from autowsgr.emulator.controller.protocol import AndroidController, DeviceInfo


if TYPE_CHECKING:
    import numpy as np


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_construction(self) -> None:
        """DeviceInfo can be constructed with serial and resolution."""
        info = DeviceInfo(serial='abc123', resolution=(1920, 1080))
        assert info.serial == 'abc123'
        assert info.resolution == (1920, 1080)

    def test_frozen_immutability(self) -> None:
        """Frozen dataclass fields cannot be modified."""
        info = DeviceInfo(serial='abc123', resolution=(1920, 1080))
        with pytest.raises(AttributeError):
            setattr(info, 'serial', 'new_serial')  # noqa: B010

    def test_slots(self) -> None:
        """DeviceInfo uses __slots__ and cannot have arbitrary attributes."""
        info = DeviceInfo(serial='abc123', resolution=(1920, 1080))
        with pytest.raises(AttributeError):
            object.__setattr__(info, 'extra_field', 'value')


class TestAndroidController:
    """Tests for AndroidController abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        """Instantiating AndroidController directly raises TypeError."""
        with pytest.raises(TypeError):
            AndroidController()

    def test_subclass_with_all_methods(self) -> None:
        """A subclass implementing all abstract methods can be instantiated."""

        class DummyController(AndroidController):
            def connect(self) -> DeviceInfo:
                return DeviceInfo(serial='dummy', resolution=(1080, 1920))

            def disconnect(self) -> None:
                pass

            @property
            def resolution(self) -> tuple[int, int]:
                return (1080, 1920)

            def screenshot(self) -> np.ndarray:
                raise NotImplementedError

            def click(self, x: float, y: float) -> None:
                pass

            def swipe(
                self,
                x1: float,
                y1: float,
                x2: float,
                y2: float,
                duration: float = 0.5,
            ) -> None:
                pass

            def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
                pass

            def key_event(self, key_code: int) -> None:
                pass

            def text(self, content: str) -> None:
                pass

            def start_app(self, package: str) -> None:
                pass

            def stop_app(self, package: str) -> None:
                pass

            def is_app_running(self, package: str) -> bool:  # noqa: ARG002
                return False

            def shell(self, cmd: str) -> str:  # noqa: ARG002
                return ''

        controller = DummyController()
        assert isinstance(controller, AndroidController)

    def test_subclass_missing_one_method(self) -> None:
        """A subclass missing an abstract method cannot be instantiated."""

        class IncompleteController(AndroidController):
            def connect(self) -> DeviceInfo:
                return DeviceInfo(serial='dummy', resolution=(1080, 1920))

            def disconnect(self) -> None:
                pass

            @property
            def resolution(self) -> tuple[int, int]:
                return (1080, 1920)

            def screenshot(self) -> np.ndarray:
                raise NotImplementedError

            def click(self, x: float, y: float) -> None:
                pass

            def swipe(
                self,
                x1: float,
                y1: float,
                x2: float,
                y2: float,
                duration: float = 0.5,
            ) -> None:
                pass

            def long_tap(self, x: float, y: float, duration: float = 1.0) -> None:
                pass

            def key_event(self, key_code: int) -> None:
                pass

            def text(self, content: str) -> None:
                pass

            def start_app(self, package: str) -> None:
                pass

            def stop_app(self, package: str) -> None:
                pass

            def is_app_running(self, package: str) -> bool:  # noqa: ARG002
                return False

            # Missing shell method

        with pytest.raises(TypeError):
            IncompleteController()

    def test_abstract_method_names_exist(self) -> None:
        """All expected abstract method names exist on AndroidController."""
        expected = [
            'connect',
            'disconnect',
            'resolution',
            'screenshot',
            'click',
            'swipe',
            'long_tap',
            'key_event',
            'text',
            'start_app',
            'stop_app',
            'is_app_running',
            'shell',
        ]
        for name in expected:
            assert hasattr(AndroidController, name)
