"""测试异常体系。"""

import pytest

from autowsgr.infra.exceptions import (
    ActionFailedError,
    AutoWSGRError,
    ConfigError,
    CriticalError,
    DockFullError,
    EmulatorConnectionError,
    EmulatorError,
    EmulatorNotFoundError,
    GameError,
    ImageNotFoundError,
    NavigationError,
    NetworkError,
    OCRError,
    PageNotFoundError,
    ResourceError,
    UIError,
    VisionError,
)


class TestExceptionHierarchy:
    """所有异常必须继承 Exception (非 BaseException) 且层级正确。"""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            AutoWSGRError,
            ConfigError,
            EmulatorError,
            EmulatorConnectionError,
            EmulatorNotFoundError,
            VisionError,
            ImageNotFoundError,
            OCRError,
            UIError,
            PageNotFoundError,
            NavigationError,
            ActionFailedError,
            GameError,
            NetworkError,
            DockFullError,
            ResourceError,
            CriticalError,
        ],
    )
    def test_inherits_exception(self, exc_cls: type):
        assert issubclass(exc_cls, Exception)
        assert issubclass(exc_cls, AutoWSGRError)

    def test_emulator_subtypes(self):
        assert issubclass(EmulatorConnectionError, EmulatorError)
        assert issubclass(EmulatorNotFoundError, EmulatorError)

    def test_vision_subtypes(self):
        assert issubclass(ImageNotFoundError, VisionError)
        assert issubclass(OCRError, VisionError)

    def test_ui_subtypes(self):
        assert issubclass(PageNotFoundError, UIError)
        assert issubclass(NavigationError, UIError)
        assert issubclass(ActionFailedError, UIError)

    def test_game_subtypes(self):
        assert issubclass(NetworkError, GameError)
        assert issubclass(DockFullError, GameError)
        assert issubclass(ResourceError, GameError)


class TestExceptionMessages:
    """测试带参数的异常信息格式。"""

    def test_image_not_found_error(self):
        err = ImageNotFoundError("main_page.png", timeout=5.0)
        assert err.template_name == "main_page.png"
        assert err.timeout == 5.0
        assert "main_page.png" in str(err)
        assert "5.0" in str(err)

    def test_image_not_found_defaults(self):
        err = ImageNotFoundError()
        assert err.template_name == ""
        assert err.timeout == 0

    def test_navigation_error(self):
        err = NavigationError("main", "map", reason="按钮不可见")
        assert err.source == "main"
        assert err.target == "map"
        assert "main" in str(err)
        assert "map" in str(err)
        assert "按钮不可见" in str(err)

    def test_navigation_error_no_reason(self):
        err = NavigationError("a", "b")
        assert "a" in str(err)
        assert "b" in str(err)

    def test_action_failed_error(self):
        err = ActionFailedError("click_attack", reason="元素未出现")
        assert err.action_name == "click_attack"
        assert "click_attack" in str(err)
        assert "元素未出现" in str(err)

    def test_action_failed_no_reason(self):
        err = ActionFailedError("swipe_left")
        assert "swipe_left" in str(err)


class TestExceptionCatchable:
    """确保异常可以被 except Exception 捕获（修复旧版 BaseException bug）。"""

    def test_catch_with_exception(self):
        with pytest.raises(Exception):
            raise ImageNotFoundError("test.png")

    def test_catch_with_base_class(self):
        with pytest.raises(AutoWSGRError):
            raise DockFullError("船坞满了")
