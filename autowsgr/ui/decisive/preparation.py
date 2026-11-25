"""决战出征准备页 UI 控制器（决战专用版）。

继承自 :class:`~autowsgr.ui.battle.preparation.BattlePreparationPage`，
仅通过 ``_use_search = False`` 切换为 "不使用搜索框" 的换船模式。

与普通换船的差异
---------------
- 普通换船: 点击搜索框 -> 输入舰船名 -> 等待筛选结果 -> 点击第一项
- 决战换船: 直接 OCR 识别选船列表 -> 按编辑距离模糊匹配 -> 点击目标坐标

这是因为决战选船流程没有搜索框（界面为直接列表展示），
且候选集合相对固定（由配置 level1/level2 决定）。

换船算法 (扫描 -> 定点更换 -> 调整次序) 由父类
:class:`~autowsgr.ui.battle.fleet_change.FleetChangeMixin` 统一提供。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

from autowsgr.combat.fleet import exact_fleet_rules
from autowsgr.constants import DECISIVE_SKILL_NAMES, ship_name_identity
from autowsgr.infra import ActionFailedError
from autowsgr.infra.logger import get_logger
from autowsgr.types import ShipDamageState
from autowsgr.ui.battle.blood import classify_blood
from autowsgr.ui.battle.constants import BLOOD_BAR_PROBE, CLICK_BACK
from autowsgr.ui.battle.preparation import BattlePreparationPage
from autowsgr.ui.decisive.legacy_fleet_change import change_fleet_legacy
from autowsgr.ui.decisive.overlay import is_decisive_map_page
from autowsgr.ui.utils import click_and_wait_for_page, recognize_ships_in_list
from autowsgr.ui.utils.navigation import NavConfig, NavigationError, check_stop
from autowsgr.vision import Color, PixelChecker


_log = get_logger('ui.decisive')


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from threading import Event

    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig
    from autowsgr.vision import OCREngine


# classic 准备页在 960x540 下的十处维修标记采样点，颜色已从 BGR 转为 RGB。
_REPAIR_SLOT_OFFSETS = (0, 111, 223, 335, 447, 559)
_REPAIR_MARKER = (
    (49, 220, Color.of(153, 55, 35)),
    (58, 220, Color.of(174, 72, 51)),
    (56, 231, Color.of(182, 63, 43)),
    (72, 220, Color.of(218, 93, 66)),
    (69, 231, Color.of(218, 93, 65)),
    (126, 222, Color.of(220, 87, 73)),
    (125, 230, Color.of(220, 92, 64)),
    (138, 221, Color.of(174, 68, 44)),
    (137, 230, Color.of(178, 68, 41)),
    (146, 232, Color.of(150, 56, 47)),
)


type RepairSnapshot = tuple[list[str | None], dict[int, ShipDamageState]]


def is_complete_fleet(fleet: Sequence[str | None], damage: Mapping[int, ShipDamageState]) -> bool:
    """逐个核对编队位置：有船时须认出舰名和伤情，舰名不能重复；空位不能有舰名或血条。"""
    names = [ship_name_identity(name) for name in fleet if name]
    return (
        len(fleet) == 6
        and set(damage) == set(range(6))
        and None not in names
        and len(set(names)) == len(names)
        and not any(name in DECISIVE_SKILL_NAMES for name in fleet)
        and all(
            isinstance(damage[i], ShipDamageState)
            and (damage[i] is ShipDamageState.NO_SHIP) == (not name)
            for i, name in enumerate(fleet)
        )
    )


def read_complete_fleet(
    page: DecisiveBattlePreparationPage, stop_event: Event, *, fresh: bool = False
) -> RepairSnapshot:
    """从同一张准备页截图核对整队舰名和伤情，画面没显示完整时再取新截图。"""
    check_stop(stop_event)
    snapshot = page.read_repair_snapshot(fresh=True) if fresh else page.read_repair_snapshot()
    deadline = time.monotonic() + 2.0
    for _ in range(5):
        if is_complete_fleet(*snapshot):
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        check_stop(stop_event)
        try:
            snapshot = page.read_repair_snapshot(fresh=True, timeout=remaining)
        except ActionFailedError:
            break
    check_stop(stop_event)
    if not is_complete_fleet(*snapshot):
        raise RuntimeError('决战准备页未能确认全部舰船的名称和伤情')
    return snapshot


class DecisiveBattlePreparationPage(BattlePreparationPage):
    """决战出征准备页面控制器（无搜索框换船版）。

    决战选船页没有搜索框，按舰船卡片的位置和名称选择目标。
    准备页在同一张画面中识别舰名和维修标记，供编队与派修复核。

    Parameters
    ----------
    ctx:
        游戏上下文。
    config:
        决战配置。
    ocr:
        OCR 引擎（必须提供，换船时依赖 OCR）。
    """

    _use_search: bool = False

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
        ocr: OCREngine | None = None,
    ) -> None:
        super().__init__(ctx, ocr)
        self._ocr: OCREngine = ocr or ctx.ocr  # type: ignore[assignment]
        self._config = config

    @staticmethod
    def detect_repair_damage(screen: np.ndarray) -> dict[int, ShipDamageState]:
        """逐舰位先检查维修标记，未命中时按血条最接近的参考色判断伤情。"""
        result = {}
        for slot, offset in enumerate(_REPAIR_SLOT_OFFSETS):
            if all(
                PixelChecker.get_pixel(screen, (x + offset + 0.5) / 960, (y + 0.5) / 540).distance(
                    color
                )
                < 30
                for x, y, color in _REPAIR_MARKER
            ):
                result[slot] = ShipDamageState.REPAIRING
            else:
                result[slot] = classify_blood(
                    PixelChecker.get_pixel(screen, *BLOOD_BAR_PROBE[slot])
                )
        return result

    def read_repair_snapshot(
        self, *, fresh: bool = False, timeout: float = 3.0
    ) -> tuple[list[str | None], dict[int, ShipDamageState]]:
        """在同一画面读取舰名和伤情；到期复查和用桶前后须取得新画面。"""
        if fresh:
            started = time.monotonic()
            baseline: np.ndarray | None = None
            while True:
                check_stop(self._ctx.stop_event)
                frame = self._ctrl.capture_frame()
                if frame.sequence is None:
                    # 缺少解码序号时，截图时间可能来自缓存；像素变化才能确认刷新。
                    if baseline is None:
                        baseline = frame.image.copy()
                    elif not np.array_equal(baseline, frame.image):
                        screen = frame.image
                        break
                elif frame.captured_at >= started:
                    screen = frame.image
                    break
                if time.monotonic() - started >= timeout:
                    raise ActionFailedError('决战维修复核未取得新的准备页画面')
                self._ctx.stop_event.wait(0.05)
        else:
            screen = self._ctrl.screenshot()
        return self.detect_fleet(screen), self.detect_repair_damage(screen)

    def read_first_screen_candidates(self) -> set[str]:
        """从首舰位打开选船页，识别首屏舰名后回到准备页。"""
        try:
            self._open_choose_page(0, stop_event=self._ctx.stop_event)
        except NavigationError as exc:
            raise TimeoutError(str(exc)) from exc
        # 离开准备页时卡片文字还在展开，稍候再读取首屏舰名。
        self._ctx.stop_event.wait(0.3)
        check_stop(self._ctx.stop_event)
        candidates = recognize_ships_in_list(self._ocr, self._ctrl.screenshot())
        self._cancel_choose_page(stop_event=self._ctx.stop_event)
        return candidates

    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: Sequence[str | None],
    ) -> bool:
        """按配置选择决战原有流程或新的换船算法。"""
        if self._config.use_new_fleet_change_algorithm:
            rules = exact_fleet_rules([name for name in ship_names if name])
            return super().change_fleet(fleet_id, rules)
        return change_fleet_legacy(self, fleet_id, ship_names)

    def go_back(self) -> None:
        """点击回退按钮 (◁)，返回**决战地图页**。

        基类 :meth:`BattlePreparationPage.go_back` 等待普通出征地图页
        (``PageName.MAP``)，而决战准备页回退后是决战地图页（不在页面
        注册表中，无 ``PageName``），沿用基类 checker 必然导航超时。
        与 :meth:`DecisiveMapController.enter_formation` 对称：checker
        直连 ``is_decisive_map_page``，source/target 仅作日志标签。
        """
        _log.debug('[UI] 决战出征准备 → 回退')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=is_decisive_map_page,
            config=NavConfig(timeout=10.0, interval=0.5),
            stop_event=self._ctx.stop_event,
            source='出征准备',
            target='决战地图',
        )
