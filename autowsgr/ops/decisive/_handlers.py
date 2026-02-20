"""决战阶段处理 Mixin。

将各阶段处理方法从 ``DecisiveController`` 主类中分离，
降低单文件复杂度（参照 :mod:`~autowsgr.combat.handlers` 的设计）。

``PhaseHandlersMixin`` 仅作为 ``DecisiveController`` 的 Mixin 使用，
不直接实例化。所有方法通过 ``self`` 访问以下属性：

    self._ctrl       : AndroidController
    self._config     : DecisiveConfig
    self._state      : DecisiveState
    self._logic      : DecisiveLogic
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from autowsgr.combat.callbacks import CombatResult
from autowsgr.combat.engine import run_combat
from autowsgr.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.ops.decisive._logic import FleetSelection
from autowsgr.ops.decisive._overlay import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SORTIE,
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
    DecisiveOverlay,
    detect_decisive_overlay,
    get_overlay_signature,
    is_advance_choice,
    is_decisive_map_page,
)
from autowsgr.ops.decisive._state import DecisivePhase
from autowsgr.types import ConditionFlag, Formation
from autowsgr.ui.battle.preparation import BattlePreparationPage, RepairStrategy
from autowsgr.vision import ApiDll, get_api_dll, PixelChecker, ROI

if TYPE_CHECKING:
    from autowsgr.combat.recognizer import ImageMatcherFunc
    from autowsgr.emulator import AndroidController
    from autowsgr.ops.decisive._config import DecisiveConfig
    from autowsgr.ops.decisive._logic import DecisiveLogic
    from autowsgr.ops.decisive._state import DecisiveState
    from autowsgr.vision import OCREngine


class PhaseHandlersMixin:
    """决战阶段处理 Mixin。

    提供所有 ``_handle_*`` 方法和辅助等待方法。
    需与 ``DecisiveController`` 组合使用（通过 MRO 继承）。
    """

    # 子类须提供这些属性（供类型检查器使用）
    _ctrl: AndroidController
    _config: DecisiveConfig
    _state: DecisiveState
    _logic: DecisiveLogic
    _image_matcher: ImageMatcherFunc | None
    _ocr: OCREngine | None
    _dll: ApiDll | None

    # ══════════════════════════════════════════════════════════════════════
    # 阶段处理方法
    # ══════════════════════════════════════════════════════════════════════

    def _handle_enter_map(self) -> None:
        """进入地图：点击出征 → 等待地图页或战备舰队弹窗。"""
        logger.info("[决战] 进入地图 (小关 {})", self._state.stage + 1)
        self._state.stage += 1
        self._state.node = "A"

        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        screen = self._poll_for_map_or_overlay(timeout=15.0)
        overlay = detect_decisive_overlay(screen)

        if overlay == DecisiveOverlay.FLEET_ACQUISITION:
            self._state.phase = DecisivePhase.CHOOSE_FLEET
        elif is_decisive_map_page(screen):
            self._state.phase = DecisivePhase.MAP_READY
        elif is_advance_choice(screen):
            self._state.phase = DecisivePhase.ADVANCE_CHOICE
        else:
            logger.warning("[决战] 进入地图后页面状态未知, 尝试继续")
            self._state.phase = DecisivePhase.MAP_READY

    def _handle_choose_fleet(self) -> None:
        """战备舰队获取：OCR 识别选项 → 购买决策 → 关闭弹窗。"""
        logger.info("[决战] 战备舰队获取")
        screen = self._ctrl.screenshot()
        selections = self._recognize_fleet_options(screen)

        if selections:
            first_node = self._state.is_begin()
            to_buy = self._logic.choose_ships(selections, first_node=first_node)
            if not to_buy:
                # 无合适选项 → 刷新一次再试
                self._ctrl.click(*CLICK_FLEET_REFRESH)
                time.sleep(1.5)
                screen = self._ctrl.screenshot()
                selections = self._recognize_fleet_options(screen)
                to_buy = self._logic.choose_ships(selections, first_node=first_node)

            for name in to_buy:
                sel = selections[name]
                self._ctrl.click(*sel.click_position)
                time.sleep(0.3)
                if name not in {"长跑训练", "肌肉记忆", "黑科技"}:
                    self._state.ships.add(name)

        self._ctrl.click(*CLICK_FLEET_CLOSE)
        time.sleep(1.0)
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_map_ready(self) -> None:
        """地图就绪：检测 overlay → 分发到对应阶段。"""
        screen = self._ctrl.screenshot()
        overlay = detect_decisive_overlay(screen)

        if overlay == DecisiveOverlay.FLEET_ACQUISITION:
            self._state.phase = DecisivePhase.CHOOSE_FLEET
        elif overlay == DecisiveOverlay.ADVANCE_CHOICE:
            self._state.phase = DecisivePhase.ADVANCE_CHOICE
        else:
            # TODO: 检查副官技能
            self._state.phase = DecisivePhase.PREPARE_COMBAT

    def _handle_advance_choice(self) -> None:
        """选择前进点：决策 → 点击卡片 → 确认。"""
        logger.info("[决战] 选择前进点")
        # TODO: OCR 识别可选节点名 (如 A1, A2)
        choice_idx = self._logic.get_advance_choice([])
        if choice_idx < len(ADVANCE_CARD_POSITIONS):
            self._ctrl.click(*ADVANCE_CARD_POSITIONS[choice_idx])
            time.sleep(0.5)
        self._ctrl.click(*CLICK_ADVANCE_CONFIRM)
        time.sleep(1.5)
        self._state.phase = DecisivePhase.MAP_READY

    def _handle_prepare_combat(self) -> None:
        """出征准备：编队 → 修理检查 → 开始出征。"""
        logger.info(
            "[决战] 出征准备 (小关 {} 节点 {})", self._state.stage, self._state.node
        )
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        best_fleet = self._logic.get_best_fleet()
        if self._logic.should_retreat(best_fleet):
            logger.info("[决战] 舰船不足, 准备撤退")
            self._state.phase = DecisivePhase.RETREAT
            return

        self._state.fleet = best_fleet

        # 编队与修理
        page = BattlePreparationPage(self._ctrl)

        # 修理: 根据配置决定修理等级
        if self._config.repair_level <= 1:
            page.apply_repair(RepairStrategy.MODERATE)
        else:
            page.apply_repair(RepairStrategy.SEVERE)

        # 检测战前血量
        screen = self._ctrl.screenshot()
        damage = page.detect_ship_damage(screen)
        self._state.ship_stats = [0] + [damage.get(i, 0) for i in range(1, 7)]

        # 出征
        page.start_battle()
        time.sleep(1.0)
        self._state.phase = DecisivePhase.IN_COMBAT

    def _handle_combat(self) -> None:
        """战斗阶段：委托 CombatEngine 执行。

        构建 BATTLE 模式的 CombatPlan，调用 run_combat 执行单节点战斗，
        将战果写入 state.ship_stats。
        """
        logger.info(
            "[决战] 开始战斗 (小关 {} 节点 {})",
            self._state.stage,
            self._state.node,
        )

        if self._image_matcher is None:
            logger.warning("[决战] 无图像匹配器, 跳过战斗")
            self._state.phase = DecisivePhase.NODE_RESULT
            return

        # 构建决战专用 CombatPlan (BATTLE 模式, 单点战斗)
        plan = CombatPlan(
            name=f"决战-{self._state.stage}-{self._state.node}",
            mode=CombatMode.BATTLE,
            default_node=NodeDecision(
                formation=Formation.double_column,
                night=True,
            ),
        )

        result = run_combat(
            self._ctrl,
            plan,
            self._image_matcher,
            ship_stats=self._state.ship_stats[:],
        )

        # 更新状态
        self._state.ship_stats = result.ship_stats[:]
        logger.info(
            "[决战] 战斗结束: {} (节点 {} 血量 {})",
            result.flag.value,
            self._state.node,
            self._state.ship_stats,
        )
        self._state.phase = DecisivePhase.NODE_RESULT

    def _handle_node_result(self) -> None:
        """节点战斗结束：推进节点，检查小关结束与修理需求。"""
        logger.info("[决战] 节点 {} 战斗结束", self._state.node)
        next_node = chr(ord(self._state.node) + 1)

        # TODO: 根据 map_end.yaml 判断小关是否真正结束
        if next_node > "J":
            self._state.phase = DecisivePhase.STAGE_CLEAR
            return

        self._state.node = next_node

        if self._logic.should_repair():
            logger.info("[决战] 需要修理")
            # TODO: 调用修理操作

        self._state.phase = DecisivePhase.MAP_READY

    def _handle_stage_clear(self) -> None:
        """小关通关：确认奖励弹窗，决定是否进入下一小关。"""
        logger.info("[决战] 小关 {} 通关!", self._state.stage)
        for _ in range(3):
            self._ctrl.click(0.5, 0.5)
            time.sleep(1.5)

        if self._state.stage >= 3:
            self._state.phase = DecisivePhase.CHAPTER_CLEAR
        else:
            self._state.phase = DecisivePhase.ENTER_MAP

    def _handle_retreat(self) -> None:
        """执行撤退：左上角撤退 → 确认退出 overlay → 点击「撤退」。"""
        logger.info("[决战] 执行撤退")
        self._go_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self._wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)
        self._ctrl.click(*CLICK_RETREAT_CONFIRM)
        time.sleep(2.0)

    def _handle_leave(self) -> None:
        """执行暂离：左上角撤退 → 确认退出 overlay → 点击「暂离」。"""
        logger.info("[决战] 执行暂离")
        self._go_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self._wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)
        self._ctrl.click(*CLICK_LEAVE)
        time.sleep(2.0)

    # ══════════════════════════════════════════════════════════════════════
    # 辅助等待方法
    # ══════════════════════════════════════════════════════════════════════

    def _go_to_map_page(self) -> None:
        """确保当前在决战地图页（若在准备页则点击左上角返回）。"""
        screen = self._ctrl.screenshot()
        if is_decisive_map_page(screen):
            return
        self._ctrl.click(0.03, 0.06)
        time.sleep(1.0)
        if not is_decisive_map_page(self._ctrl.screenshot()):
            logger.warning("[决战] 无法确认已回到地图页")

    def _poll_for_map_or_overlay(
        self,
        timeout: float = 15.0,
        interval: float = 0.5,
    ) -> np.ndarray:
        """轮询截图，直到出现地图页或任意 overlay，返回该截图。"""
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if is_decisive_map_page(screen) or detect_decisive_overlay(screen) is not None:
                return screen
            if time.monotonic() >= deadline:
                logger.warning("[决战] 等待地图页/overlay 超时")
                return screen
            time.sleep(interval)

    def _wait_for_overlay(
        self,
        target: DecisiveOverlay,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> np.ndarray:
        """反复截图直到指定 overlay 出现，超时则抛出 ``TimeoutError``。"""
        sig = get_overlay_signature(target)
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if PixelChecker.check_signature(screen, sig):
                return screen
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"等待 overlay {target.value} 超时 ({timeout}s)"
                )
            time.sleep(interval)

    # ══════════════════════════════════════════════════════════════════════
    # OCR / DLL 识别
    # ══════════════════════════════════════════════════════════════════════

    def _recognize_fleet_options(
        self,
        screen: np.ndarray,
    ) -> dict[str, FleetSelection]:
        """OCR 识别战备舰队获取界面的 5 个可选项。

        移植自旧代码 ``decisive_battle.py`` 的 ``choose()`` 方法。

        流程::

            1. 裁切右上角资源区域 → 识别可用分数 → 写入 state.score
            2. 裁切底部费用整行   → 识别每张卡的费用
            3. 对可负担的卡裁切名称区域  → 识别舰船名
            4. 组装 {name: FleetSelection}

        Returns
        -------
        dict[str, FleetSelection]
            可购买项字典；无 OCR 引擎时返回 ``{}``。
        """
        if self._ocr is None:
            logger.warning("[决战] 无 OCR 引擎, 跳过舰队选择")
            return {}

        h, w = screen.shape[:2]

        # 1. 识别可用分数
        res_roi = ROI(
            x1=RESOURCE_AREA[0][0], y1=RESOURCE_AREA[1][1],
            x2=RESOURCE_AREA[1][0], y2=RESOURCE_AREA[0][1],
        )
        score_img = res_roi.crop(screen)
        score_val = self._ocr.recognize_number(score_img)
        if score_val is not None:
            self._state.score = score_val
            logger.debug("[决战] 可用分数: {}", score_val)
        else:
            logger.warning("[决战] 分数 OCR 失败, 使用默认值: {}", self._state.score)

        # 2. 识别费用整行
        cost_roi = ROI(
            x1=COST_AREA[0][0], y1=COST_AREA[1][1],
            x2=COST_AREA[1][0], y2=COST_AREA[0][1],
        )
        cost_img = cost_roi.crop(screen)
        cost_results = self._ocr.recognize(cost_img, allowlist="0123456789x")

        # 解析费用: 取每个 OCR 结果中的数字
        costs: list[int] = []
        for r in cost_results:
            text = r.text.strip().lstrip("xX")
            try:
                costs.append(int(text))
            except (ValueError, TypeError):
                logger.debug("[决战] 费用解析跳过: '{}'", r.text)

        logger.debug("[决战] 识别到 {} 项费用: {}", len(costs), costs)

        # 3. 对可负担的卡识别舰船名
        score = self._state.score
        ship_names = self._config.level1 + self._config.level2 + [
            "长跑训练", "肌肉记忆", "黑科技",
        ]
        selections: dict[str, FleetSelection] = {}

        for i, cost in enumerate(costs):
            if cost > score:
                continue
            if i >= len(SHIP_NAME_X_RANGES):
                break

            # 裁切舰船名区域
            x_range = SHIP_NAME_X_RANGES[i]
            y_range = SHIP_NAME_Y_RANGE
            name_roi = ROI(x1=x_range[0], y1=y_range[0], x2=x_range[1], y2=y_range[1])
            name_img = name_roi.crop(screen)

            name = self._ocr.recognize_ship_name(name_img, ship_names)
            if name is None:
                # fallback: 直接用 OCR 文本
                raw = self._ocr.recognize_single(name_img)
                name = raw.text.strip() if raw.text.strip() else f"未识别_{i}"
                logger.debug("[决战] 舰船名模糊匹配失败, 原文: '{}'", name)

            click_x = FLEET_CARD_X_POSITIONS[i] if i < len(FLEET_CARD_X_POSITIONS) else 0.5
            click_y = FLEET_CARD_CLICK_Y

            selections[name] = FleetSelection(
                name=name,
                cost=cost,
                click_position=(click_x, click_y),
            )

        logger.info("[决战] 舰队选项: {}", {k: v.cost for k, v in selections.items()})
        return selections

    def _recognize_node(self, screen: np.ndarray) -> str:
        """DLL 识别当前决战节点字母 (如 'A', 'B')。

        移植自旧代码 ``decisive_battle.py`` 的 ``recognize_node()``:
        查找舰船图标位置 → 裁切该列图像 → DLL ``recognize_map()``。

        Returns
        -------
        str
            节点字母；识别失败时返回当前 ``state.node``。
        """
        dll = self._dll
        if dll is None:
            try:
                dll = get_api_dll()
            except FileNotFoundError:
                logger.warning("[决战] 无 DLL, 跳过节点识别")
                return self._state.node

        # 使用 image_matcher 查找舰船图标位置
        # 旧代码: position = timer.wait_images_position(IMG.fight_image[18:20])
        # 这里简化：在当前截图中搜索图标位置
        if self._image_matcher is not None:
            match_result = self._image_matcher(screen)
            if match_result is not None:
                logger.debug("[决战] 图标匹配结果: {}", match_result)

        # 裁切整列图像用于 DLL 识别（与旧代码一致）
        # 旧代码: crop_rectangle_relative(screen, pos_x/960 - 0.03, 0, 0.042, 1)
        # 简化: 使用屏幕中心偏左的列区域
        h, w = screen.shape[:2]
        # 默认使用 x=0.5 附近的列
        x_center = 0.47
        col_width = 0.042
        x1 = max(0, int((x_center - col_width / 2) * w))
        x2 = min(w, int((x_center + col_width / 2) * w))
        col_crop = screen[0:h, x1:x2]

        try:
            result = dll.recognize_map(col_crop)
            if result != "0":
                logger.info("[决战] DLL 节点识别: {}", result)
                return result
        except Exception:
            logger.warning("[决战] DLL 节点识别异常", exc_info=True)

        logger.debug("[决战] 节点识别失败, 保持: {}", self._state.node)
        return self._state.node
