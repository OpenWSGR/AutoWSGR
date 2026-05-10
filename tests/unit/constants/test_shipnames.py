"""测试 autowsgr.constants.shipnames。"""

from __future__ import annotations

import copy

from autowsgr.constants.shipnames import (
    DECISIVE_SKILL_NAMES,
    SHIPNAMES,
    process_dict,
    update_shipnames,
)


def test_process_dict_nested_lists() -> None:
    """process_dict 应正确展平嵌套列表值。"""
    d = {'a': ['x', 'y'], 'b': ['z']}
    assert process_dict(d) == ['x', 'y', 'z']


def test_process_dict_empty_dict() -> None:
    """process_dict 对空字典应返回空列表。"""
    assert process_dict({}) == []


def test_process_dict_single_key() -> None:
    """process_dict 对单键字典应返回其值列表。"""
    d = {'ships': ['ship_a', 'ship_b', 'ship_c']}
    assert process_dict(d) == ['ship_a', 'ship_b', 'ship_c']


def test_decisive_skill_names_values() -> None:
    """DECISIVE_SKILL_NAMES 应包含预期值。"""
    assert DECISIVE_SKILL_NAMES == ['长跑训练', '肌肉记忆', '黑科技']


def test_shipnames_is_non_empty_list_of_strings() -> None:
    """SHIPNAMES 应为非空字符串列表。"""
    assert isinstance(SHIPNAMES, list)
    assert len(SHIPNAMES) > 0
    assert all(isinstance(name, str) for name in SHIPNAMES)


class TestUpdateShipnames:
    """update_shipnames 测试（涉及全局状态，需隔离）。"""

    def setup_method(self) -> None:
        self._backup = copy.deepcopy(SHIPNAMES)

    def teardown_method(self) -> None:
        SHIPNAMES[:] = self._backup

    def test_prepend_order(self) -> None:
        """新名称应按顺序前置到 SHIPNAMES 前端。"""
        original_len = len(SHIPNAMES)
        update_shipnames(['__test_new_a__', '__test_new_b__'])
        assert SHIPNAMES[:2] == ['__test_new_a__', '__test_new_b__']
        assert len(SHIPNAMES) == original_len + 2

    def test_deduplication(self) -> None:
        """重复名称不应被再次添加。"""
        original_first = SHIPNAMES[0]
        original_len = len(SHIPNAMES)
        update_shipnames([original_first, '__test_unique__'])
        assert SHIPNAMES[0] == '__test_unique__'
        assert SHIPNAMES[1] == original_first
        assert len(SHIPNAMES) == original_len + 1

    def test_empty_list(self) -> None:
        """传入空列表不应改变 SHIPNAMES。"""
        original = copy.deepcopy(SHIPNAMES)
        update_shipnames([])
        assert original == SHIPNAMES

    def test_idempotency(self) -> None:
        """相同额外列表多次调用结果应一致（不重复添加）。"""
        extra = ['__test_idem_a__', '__test_idem_b__']
        update_shipnames(extra)
        first_state = copy.deepcopy(SHIPNAMES)
        update_shipnames(extra)
        assert first_state == SHIPNAMES
