"""测试 autowsgr.vision.pixel."""

from __future__ import annotations

import pytest

from autowsgr.vision.pixel import (
    Color,
    CompositePixelSignature,
    MatchStrategy,
    PixelDetail,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
)


class TestColor:
    """Color 构造、转换与距离计算。"""

    def test_constructor(self) -> None:
        c = Color(r=10, g=20, b=30)
        assert c.r == 10
        assert c.g == 20
        assert c.b == 30

    def test_of(self) -> None:
        c = Color.of(1, 2, 3)
        assert c == Color(1, 2, 3)

    def test_from_rgb(self) -> None:
        c = Color.from_rgb(4, 5, 6)
        assert c == Color(4, 5, 6)

    def test_from_bgr(self) -> None:
        c = Color.from_bgr(30, 20, 10)
        assert c == Color(10, 20, 30)

    def test_from_rgb_tuple(self) -> None:
        c = Color.from_rgb_tuple((10, 20, 30))
        assert c == Color(10, 20, 30)

    def test_from_bgr_tuple(self) -> None:
        c = Color.from_bgr_tuple((30, 20, 10))
        assert c == Color(10, 20, 30)

    def test_as_rgb_tuple(self) -> None:
        c = Color(1, 2, 3)
        assert c.as_rgb_tuple() == (1, 2, 3)

    def test_as_bgr_tuple(self) -> None:
        c = Color(1, 2, 3)
        assert c.as_bgr_tuple() == (3, 2, 1)

    def test_frozen(self) -> None:
        c = Color(1, 2, 3)
        with pytest.raises(AttributeError):
            c.r = 10  # ty: ignore[invalid-assignment]

    def test_repr(self) -> None:
        assert repr(Color(1, 2, 3)) == 'Color(r=1, g=2, b=3)'

    def test_distance_zero(self) -> None:
        c = Color(100, 100, 100)
        assert c.distance(c) == 0.0

    def test_distance_nonzero(self) -> None:
        a = Color(0, 0, 0)
        b = Color(3, 4, 0)
        assert a.distance(b) == 5.0

    def test_distance_3d(self) -> None:
        a = Color(1, 2, 2)
        b = Color(4, 6, 7)
        expected = ((3) ** 2 + (4) ** 2 + (5) ** 2) ** 0.5
        assert a.distance(b) == pytest.approx(expected)

    def test_near_exact(self) -> None:
        a = Color(100, 100, 100)
        assert a.near(a) is True

    def test_near_within_tolerance(self) -> None:
        a = Color(0, 0, 0)
        b = Color(3, 4, 0)
        assert a.near(b, tolerance=5.0) is True

    def test_near_at_boundary(self) -> None:
        a = Color(0, 0, 0)
        b = Color(3, 4, 0)
        assert a.near(b, tolerance=5.0) is True

    def test_near_outside_tolerance(self) -> None:
        a = Color(0, 0, 0)
        b = Color(3, 4, 0)
        assert a.near(b, tolerance=4.9) is False

    def test_near_default_tolerance(self) -> None:
        a = Color(0, 0, 0)
        b = Color(20, 20, 0)
        dist = a.distance(b)
        assert a.near(b) is (dist <= 30.0)


class TestPixelRule:
    """PixelRule 构造与字典序列化。"""

    def test_constructor_defaults(self) -> None:
        rule = PixelRule(x=0.5, y=0.5, color=Color(1, 2, 3))
        assert rule.x == 0.5
        assert rule.y == 0.5
        assert rule.color == Color(1, 2, 3)
        assert rule.tolerance == 30.0

    def test_of(self) -> None:
        rule = PixelRule.of(0.1, 0.2, (10, 20, 30), tolerance=15.0)
        assert rule.x == 0.1
        assert rule.y == 0.2
        assert rule.color == Color(10, 20, 30)
        assert rule.tolerance == 15.0

    def test_to_dict_round_trip(self) -> None:
        rule = PixelRule(x=0.5, y=0.85, color=Color(201, 129, 54), tolerance=40.0)
        d = rule.to_dict()
        restored = PixelRule.from_dict(d)
        assert restored == rule

    def test_from_dict_with_list_color(self) -> None:
        d = {'x': 0.5, 'y': 0.85, 'color': [201, 129, 54]}
        rule = PixelRule.from_dict(d)
        assert rule.color == Color(201, 129, 54)
        assert rule.tolerance == 30.0

    def test_from_dict_with_tuple_color(self) -> None:
        d = {'x': 0.5, 'y': 0.85, 'color': (201, 129, 54), 'tolerance': 25.0}
        rule = PixelRule.from_dict(d)
        assert rule.color == Color(201, 129, 54)
        assert rule.tolerance == 25.0

    def test_from_dict_with_dict_color(self) -> None:
        d = {'x': 0.1, 'y': 0.2, 'color': {'r': 1, 'g': 2, 'b': 3}, 'tolerance': 10.0}
        rule = PixelRule.from_dict(d)
        assert rule.color == Color(1, 2, 3)
        assert rule.tolerance == 10.0

    def test_from_dict_invalid_color_type(self) -> None:
        d = {'x': 0.0, 'y': 0.0, 'color': 'not_a_color'}
        with pytest.raises(TypeError):
            PixelRule.from_dict(d)

    def test_frozen(self) -> None:
        rule = PixelRule(x=0.0, y=0.0, color=Color(0, 0, 0))
        with pytest.raises(AttributeError):
            rule.x = 1.0  # ty: ignore[invalid-assignment]


class TestMatchStrategy:
    """MatchStrategy 枚举值。"""

    def test_all(self) -> None:
        assert MatchStrategy.ALL.value == 'all'

    def test_any(self) -> None:
        assert MatchStrategy.ANY.value == 'any'

    def test_count(self) -> None:
        assert MatchStrategy.COUNT.value == 'count'

    def test_membership(self) -> None:
        assert set(MatchStrategy) == {MatchStrategy.ALL, MatchStrategy.ANY, MatchStrategy.COUNT}


class TestPixelSignature:
    """PixelSignature 构造、转换与长度。"""

    def test_constructor_defaults(self) -> None:
        sig = PixelSignature(name='test', rules=())
        assert sig.name == 'test'
        assert sig.rules == ()
        assert sig.strategy == MatchStrategy.ALL
        assert sig.threshold == 0

    def test_list_to_tuple_conversion(self) -> None:
        rules = [PixelRule.of(0.1, 0.2, (1, 2, 3))]
        sig = PixelSignature(name='test', rules=rules)
        assert isinstance(sig.rules, tuple)
        assert sig.rules == tuple(rules)

    def test_len(self) -> None:
        sig = PixelSignature(
            name='test',
            rules=[
                PixelRule.of(0.1, 0.2, (1, 2, 3)),
                PixelRule.of(0.3, 0.4, (4, 5, 6)),
            ],
        )
        assert len(sig) == 2

    def test_len_empty(self) -> None:
        sig = PixelSignature(name='empty', rules=())
        assert len(sig) == 0

    def test_from_dict_to_dict_round_trip(self) -> None:
        sig = PixelSignature(
            name='main_page',
            rules=[
                PixelRule.of(0.1, 0.2, (1, 2, 3), tolerance=25.0),
                PixelRule.of(0.3, 0.4, (4, 5, 6)),
            ],
            strategy=MatchStrategy.COUNT,
            threshold=1,
        )
        d = sig.to_dict()
        restored = PixelSignature.from_dict(d)
        assert restored == sig

    def test_from_dict_default_strategy_and_threshold(self) -> None:
        d = {
            'name': 'default_sig',
            'rules': [{'x': 0.5, 'y': 0.5, 'color': [10, 20, 30]}],
        }
        sig = PixelSignature.from_dict(d)
        assert sig.strategy == MatchStrategy.ALL
        assert sig.threshold == 0
        assert len(sig) == 1

    def test_frozen(self) -> None:
        sig = PixelSignature(name='test', rules=())
        with pytest.raises(AttributeError):
            sig.name = 'changed'  # ty: ignore[invalid-assignment]


class TestCompositePixelSignature:
    """CompositePixelSignature 构造、转换与长度。"""

    def test_constructor_list_to_tuple(self) -> None:
        sigs = [PixelSignature(name='a', rules=[PixelRule.of(0.1, 0.2, (1, 2, 3))])]
        comp = CompositePixelSignature(name='comp', signatures=sigs)
        assert isinstance(comp.signatures, tuple)
        assert comp.signatures == tuple(sigs)

    def test_len(self) -> None:
        comp = CompositePixelSignature(
            name='comp',
            signatures=[
                PixelSignature(name='a', rules=[PixelRule.of(0.1, 0.2, (1, 2, 3))]),
                PixelSignature(
                    name='b',
                    rules=[
                        PixelRule.of(0.3, 0.4, (4, 5, 6)),
                        PixelRule.of(0.5, 0.6, (7, 8, 9)),
                    ],
                ),
            ],
        )
        assert len(comp) == 3

    def test_len_empty(self) -> None:
        comp = CompositePixelSignature(name='empty', signatures=())
        assert len(comp) == 0

    def test_any_of(self) -> None:
        a = PixelSignature(name='a', rules=[PixelRule.of(0.1, 0.2, (1, 2, 3))])
        b = PixelSignature(name='b', rules=[PixelRule.of(0.3, 0.4, (4, 5, 6))])
        comp = CompositePixelSignature.any_of('either', a, b)
        assert comp.name == 'either'
        assert comp.signatures == (a, b)
        assert len(comp) == 2

    def test_frozen(self) -> None:
        comp = CompositePixelSignature(name='test', signatures=())
        with pytest.raises(AttributeError):
            comp.name = 'changed'  # ty: ignore[invalid-assignment]


class TestPixelDetail:
    """PixelDetail 纯数据类。"""

    def test_attributes(self) -> None:
        rule = PixelRule.of(0.1, 0.2, (1, 2, 3))
        actual = Color(4, 5, 6)
        detail = PixelDetail(rule=rule, actual=actual, distance=5.0, matched=True)
        assert detail.rule == rule
        assert detail.actual == actual
        assert detail.distance == 5.0
        assert detail.matched is True

    def test_frozen(self) -> None:
        detail = PixelDetail(
            rule=PixelRule.of(0.0, 0.0, (0, 0, 0)),
            actual=Color(0, 0, 0),
            distance=0.0,
            matched=False,
        )
        with pytest.raises(AttributeError):
            detail.matched = True  # ty: ignore[invalid-assignment]


class TestPixelMatchResult:
    """PixelMatchResult 布尔值与比例计算。"""

    def test_bool_true(self) -> None:
        result = PixelMatchResult(
            matched=True,
            signature_name='sig',
            matched_count=2,
            total_count=2,
        )
        assert bool(result) is True

    def test_bool_false(self) -> None:
        result = PixelMatchResult(
            matched=False,
            signature_name='sig',
            matched_count=0,
            total_count=2,
        )
        assert bool(result) is False

    def test_ratio_full_match(self) -> None:
        result = PixelMatchResult(
            matched=True,
            signature_name='sig',
            matched_count=4,
            total_count=4,
        )
        assert result.ratio == 1.0

    def test_ratio_partial_match(self) -> None:
        result = PixelMatchResult(
            matched=True,
            signature_name='sig',
            matched_count=1,
            total_count=4,
        )
        assert result.ratio == 0.25

    def test_ratio_zero_total(self) -> None:
        result = PixelMatchResult(
            matched=False,
            signature_name='sig',
            matched_count=0,
            total_count=0,
        )
        assert result.ratio == 0.0

    def test_ratio_zero_matched(self) -> None:
        result = PixelMatchResult(
            matched=False,
            signature_name='sig',
            matched_count=0,
            total_count=5,
        )
        assert result.ratio == 0.0

    def test_details_default(self) -> None:
        result = PixelMatchResult(
            matched=True,
            signature_name='sig',
            matched_count=1,
            total_count=1,
        )
        assert result.details == ()

    def test_frozen(self) -> None:
        result = PixelMatchResult(
            matched=True,
            signature_name='sig',
            matched_count=1,
            total_count=1,
        )
        with pytest.raises(AttributeError):
            result.matched = False  # ty: ignore[invalid-assignment]
