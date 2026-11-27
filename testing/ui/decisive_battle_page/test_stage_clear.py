"""用确定的控件观测验证结算协议，不依赖实机截图、舰船掉落或 OCR 模型。"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from autowsgr.emulator.frame import CapturedFrame
from autowsgr.image_resources import Templates
from autowsgr.ui.decisive import map_controller as module
from autowsgr.ui.decisive.map_controller import DecisiveMapController


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from autowsgr.vision.image_template import ImageTemplate


_CLEAR = ('clear_title', 'clear_abandon', 'clear_confirm')
_DROP = ('drop_menu', 'drop_dialog')


def _reward_screen(menu: ImageTemplate | None, *, dialogue: bool) -> np.ndarray:
    """真实模板合成的720p画面，只验证模板与布局契约，不代表实机准确率。"""
    image = np.full((720, 1280, 3), 40, dtype=np.uint8)
    elements = ([] if menu is None else [(menu, 15, 540)]) + (
        [(Templates.Decisive.REWARD_DIALOG_CORNER, 1020, 650)] if dialogue else []
    )
    for template, x, y in elements:
        src_w, src_h = template.source_resolution
        patch = cv2.resize(
            template.image,
            (round(template.width * 1280 / src_w), round(template.height * 720 / src_h)),
        )
        height, width = patch.shape[:2]
        image[y : y + height, x : x + width] = patch
    return image


@pytest.fixture
def controller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DecisiveMapController:
    ctrl = DecisiveMapController.__new__(DecisiveMapController)
    ctrl._ctrl = MagicMock()
    ctrl._ocr = MagicMock(side_effect=AssertionError('Unexpected OCR model dependency'))
    ctrl._ctx = SimpleNamespace(
        stop_event=threading.Event(),
        config=SimpleNamespace(log=SimpleNamespace(dir=tmp_path)),
    )
    elapsed = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(
        module.time, 'sleep', lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
    )
    ctrl._STAGE_CLEAR_TIMEOUT = 3.0
    return ctrl


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch) -> Callable[..., np.ndarray]:
    """小数组仅标识观测；模拟底层匹配结果，不声称验证实图识别准确率。"""
    observations: list[tuple[set[str], bool]] = []
    controls = {
        Templates.Decisive.STAGE_CLEAR_TITLE.name: 'clear_title',
        Templates.Decisive.STAGE_CLEAR_ABANDON.name: 'clear_abandon',
        Templates.Confirm.CONFIRM_4.name: 'clear_confirm',
        Templates.Confirm.CONFIRM_1.name: 'reward_confirm',
        Templates.Symbol.GET_SHIP.name: 'drop_menu',
        Templates.Decisive.REWARD_DIALOG_CORNER.name: 'drop_dialog',
        Templates.Decisive.ENTRY_CHALLENGING.name: 'entry',
    }
    centers = {'clear_confirm': (0.502, 0.847), 'reward_confirm': (0.502, 0.566)}

    def make(*visible: str, selected: bool = True) -> np.ndarray:
        index = len(observations)
        observations.append((set(visible), selected))
        return np.full((8, 8, 3), index, dtype=np.uint8)

    def find(
        image: np.ndarray, template: ImageTemplate, **_kwargs: object
    ) -> SimpleNamespace | None:
        visible, _ = observations[int(image[0, 0, 0])]
        control = controls.get(template.name)
        if control not in visible:
            return None
        return SimpleNamespace(center=centers.get(control, (0.5, 0.9)))

    def find_any(
        image: np.ndarray, templates: Iterable[ImageTemplate], **kwargs: object
    ) -> SimpleNamespace | None:
        return next((match for item in templates if (match := find(image, item, **kwargs))), None)

    monkeypatch.setattr(module.ImageChecker, 'find_template', find)
    monkeypatch.setattr(module.ImageChecker, 'find_any', find_any)
    monkeypatch.setattr(
        module.ImageChecker,
        'template_exists',
        lambda image, template, **kwargs: find(image, template, **kwargs) is not None,
    )
    monkeypatch.setattr(
        module.PixelChecker,
        'check_signature',
        lambda image, _: SimpleNamespace(matched=observations[int(image[0, 0, 0])][1]),
    )
    return make


@pytest.mark.parametrize('missing', [None, *_CLEAR])
def test_clear_requires_both_titles_and_confirmation_button(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    missing: str | None,
) -> None:
    image = screen(*(control for control in _CLEAR if control != missing))
    assert controller.is_stage_clear(image) is (missing is None)
    controller._ocr.assert_not_called()


@pytest.mark.parametrize('visible', [(), ('drop_menu',), ('drop_dialog',), _DROP])
def test_drop_requires_menu_and_complete_dialogue(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    visible: tuple[str, ...],
) -> None:
    assert controller._has_reward_drop(screen(*visible)) is (visible == _DROP)


@pytest.mark.parametrize('menu', [Templates.Symbol.GET_SHIP, Templates.Symbol.GET_ITEM, None])
@pytest.mark.parametrize('dialogue', [False, True])
def test_real_reward_templates_require_menu_and_dialogue(
    controller: DecisiveMapController, menu: ImageTemplate | None, dialogue: bool
) -> None:
    image = _reward_screen(menu, dialogue=dialogue)

    assert controller._has_reward_drop(image) is (menu is not None and dialogue)


def test_item_reward_can_resume_settlement_with_real_templates(
    controller: DecisiveMapController, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = _reward_screen(Templates.Symbol.GET_ITEM, dialogue=True)
    entry = np.full((720, 1280, 3), 40, dtype=np.uint8)
    template = Templates.Decisive.ENTRY_CHALLENGING
    patch = cv2.resize(
        template.image,
        (round(template.width * 1280 / 960), round(template.height * 720 / 540)),
    )
    height, width = patch.shape[:2]
    entry[600 : 600 + height, 500 : 500 + width] = patch
    controller._ctrl.capture_frame.side_effect = [
        CapturedFrame(image, 1, 1.0),
        CapturedFrame(entry, 2, 2.0),
        CapturedFrame(entry, 3, 3.0),
    ]
    # 物品没有舰名，反馈识别失败不影响已确认奖励页的继续按钮。
    monkeypatch.setattr(
        'autowsgr.combat.recognize_ship_drop', MagicMock(side_effect=RuntimeError('not a ship'))
    )

    assert controller.confirm_stage_clear(resume_rewards=True) == []
    controller._ctrl.click.assert_called_once_with(0.953, 0.954)


def test_clear_without_visible_confirmation_button_is_not_actionable(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    image = screen('clear_title', 'clear_abandon')
    assert not controller.is_stage_clear(image)
    assert controller.detect_decisive_phase(image) is None
    controller._ctrl.capture_frame.return_value = CapturedFrame(image, 1, 1.0)
    with pytest.raises(RuntimeError, match='拒绝结算操作'):
        controller.confirm_stage_clear()
    controller._ctrl.click.assert_not_called()
    assert list((Path(controller._ctx.config.log.dir) / 'images').glob('decisive-clear-error*.png'))


def test_clear_transition_cannot_become_a_stable_normal_map(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = screen('clear_title', 'clear_abandon')
    normal = screen()
    final = CapturedFrame(normal, 4, 4.0)
    controller._ctrl.capture_frame.side_effect = [
        CapturedFrame(pending, 1, 1.0),
        CapturedFrame(pending, 2, 2.0),
        CapturedFrame(normal, 3, 3.0),
        final,
    ]
    monkeypatch.setattr(module, 'is_decisive_map_page', lambda _: True)
    monkeypatch.setattr(module, 'detect_decisive_overlay', lambda _: None)
    monkeypatch.setattr(controller, '_locate_ship_icon', lambda _: None)
    assert controller.wait_for_stable_map_frame() is final


def test_settlement_checks_each_control_and_waits_for_two_fresh_entry_frames(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drop = MagicMock(return_value=SimpleNamespace(ship_name='测试舰甲'))
    monkeypatch.setattr('autowsgr.combat.recognize_ship_drop', drop)
    clear = CapturedFrame(screen(*_CLEAR), 1, 1.0)
    entry = CapturedFrame(screen('entry'), 5, 5.0)
    controller._ctrl.capture_frame.side_effect = [
        clear,
        clear,  # 缓存帧不能重复确认。
        CapturedFrame(screen(), 2, 2.0),  # 过场不能盲点。
        CapturedFrame(screen('reward_confirm'), 3, 3.0),
        CapturedFrame(screen(*_DROP), 4, 4.0),
        entry,
        entry,
        CapturedFrame(screen('entry'), 6, 6.0),
    ]
    assert controller.confirm_stage_clear() == ['测试舰甲']
    assert [call.args for call in controller._ctrl.click.call_args_list] == [
        (0.502, 0.847),
        (0.502, 0.566),
        (0.953, 0.954),
    ]
    assert controller._ctrl.capture_frame.call_count == 8


@pytest.mark.parametrize(
    ('ship_name', 'ocr_fails'),
    [('测试舰甲', False), ('测试舰乙', False), ('', False), (None, True)],
)
def test_drop_advances_only_on_continue_click_regardless_of_ship_name(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
    ship_name: str | None,
    ocr_fails: bool,
) -> None:
    """后续页面只由正确点击产生，避免预设连续截图掩盖错误点击区域。"""
    drop = MagicMock(return_value=SimpleNamespace(ship_name=ship_name))
    if ocr_fails:
        drop.side_effect = RuntimeError('OCR unavailable')
    monkeypatch.setattr('autowsgr.combat.recognize_ship_drop', drop)
    screens = [screen(*_CLEAR), screen('reward_confirm'), screen(*_DROP), screen('entry')]
    state = {'page': 0, 'sequence': 0}

    def capture() -> CapturedFrame:
        state['sequence'] += 1
        return CapturedFrame(screens[state['page']], state['sequence'], float(state['sequence']))

    def click(x: float, y: float) -> None:
        if state['page'] == 0 and 0.45 < x < 0.55 and 0.8 < y < 0.9:
            state['page'] = 1
        elif state['page'] == 1 and 0.45 < x < 0.55 and 0.5 < y < 0.6:
            state['page'] = 2
        elif state['page'] == 2 and 0.92 < x < 0.98 and 0.92 < y < 0.98:
            state['page'] = 3

    controller._ctrl.capture_frame.side_effect = capture
    controller._ctrl.click.side_effect = click
    assert controller.confirm_stage_clear() == ([ship_name] if ship_name else [])
    assert state['page'] == 3
    assert controller._ctrl.click.call_count == 3
    drop.assert_called_once()


def test_ship_menu_without_finished_dialogue_does_not_trigger_continue(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    image = screen('drop_menu')
    controller._ctrl.capture_frame.side_effect = [
        CapturedFrame(screen(*_CLEAR), 0, 0.0),
        *[CapturedFrame(image, index, float(index)) for index in range(1, 30)],
    ]
    with pytest.raises(RuntimeError, match='未确认返回入口页'):
        controller.confirm_stage_clear()
    controller._ctrl.click.assert_called_once()


def test_explicit_reward_resume_requires_and_advances_complete_drop(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'autowsgr.combat.recognize_ship_drop',
        lambda *_args, **_kwargs: SimpleNamespace(ship_name='测试舰乙'),
    )
    state = {'continued': False, 'sequence': 0}
    drop, entry = screen(*_DROP), screen('entry')

    def capture() -> CapturedFrame:
        state['sequence'] += 1
        image = entry if state['continued'] else drop
        return CapturedFrame(image, state['sequence'], float(state['sequence']))

    def click(x: float, y: float) -> None:
        if 0.92 < x < 0.98 and 0.92 < y < 0.98:
            state['continued'] = True

    controller._ctrl.capture_frame.side_effect = capture
    controller._ctrl.click.side_effect = click
    assert controller.confirm_stage_clear(resume_rewards=True) == ['测试舰乙']
    controller._ctrl.click.assert_called_once_with(0.953, 0.954)
    assert controller._ctrl.capture_frame.call_count == 3


@pytest.mark.parametrize('visible', [_CLEAR, ('reward_confirm',), (), ('entry',), ('drop_menu',)])
def test_reward_resume_rejects_other_initial_pages(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
    visible: tuple[str, ...],
) -> None:
    controller._ctrl.capture_frame.return_value = CapturedFrame(screen(*visible), 1, 1.0)
    with pytest.raises(RuntimeError, match='拒绝恢复'):
        controller.confirm_stage_clear(resume_rewards=True)
    controller._ctrl.click.assert_not_called()
    assert list((Path(controller._ctx.config.log.dir) / 'images').glob('decisive-clear-error*.png'))


def test_default_settlement_does_not_accept_drop_as_stage_clear(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    controller._ctrl.capture_frame.return_value = CapturedFrame(screen(*_DROP), 1, 1.0)
    with pytest.raises(RuntimeError, match='拒绝结算操作'):
        controller.confirm_stage_clear()
    controller._ctrl.click.assert_not_called()


def test_settlement_cannot_finish_at_unrecognized_page(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    first = CapturedFrame(screen(*_CLEAR), 1, 1.0)
    unknown = CapturedFrame(screen(), 2, 2.0)
    controller._ctrl.capture_frame.side_effect = [first, *([unknown] * 70)]
    with pytest.raises(RuntimeError, match='未确认返回入口页'):
        controller.confirm_stage_clear()
    controller._ctrl.click.assert_called_once()


def test_entry_confirmation_requires_consecutive_frames(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    pages = [screen(*_CLEAR), screen('entry'), screen(), screen('entry'), screen('entry')]
    controller._ctrl.capture_frame.side_effect = [
        CapturedFrame(image, index, float(index)) for index, image in enumerate(pages)
    ]
    assert controller.confirm_stage_clear() == []
    assert controller._ctrl.capture_frame.call_count == 5


def test_unselected_clear_card_is_selected_before_confirmation(
    controller: DecisiveMapController,
    screen: Callable[..., np.ndarray],
) -> None:
    controller._ctrl.capture_frame.side_effect = [
        CapturedFrame(screen(*_CLEAR, selected=False), 1, 1.0),
        CapturedFrame(screen(*_CLEAR), 2, 2.0),
        CapturedFrame(screen('entry'), 3, 3.0),
        CapturedFrame(screen('entry'), 4, 4.0),
    ]
    assert controller.confirm_stage_clear() == []
    assert controller._ctrl.click.call_args_list[0].args == (0.31, 0.48)
    assert controller._ctrl.click.call_args_list[1].args == (0.502, 0.847)


def test_stop_before_settlement_has_no_device_actions(controller: DecisiveMapController) -> None:
    controller._ctx.stop_event.set()
    with pytest.raises(InterruptedError):
        controller.confirm_stage_clear()
    controller._ctrl.capture_frame.assert_not_called()
    controller._ctrl.click.assert_not_called()
