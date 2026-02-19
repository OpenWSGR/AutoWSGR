"""测试异常体系。"""

import pytest

from autowsgr.infra.exceptions import (
    ActionFailedError,
    ImageNotFoundError,
    NavigationError,
)


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


