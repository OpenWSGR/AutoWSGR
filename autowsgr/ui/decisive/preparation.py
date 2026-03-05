"""决战出征准备页 UI 控制器（决战专用版）。

继承自 :class:`~autowsgr.ui.battle.preparation.BattlePreparationPage`，
覆盖换船逻辑：**不使用搜索框输入舰船名**，而是在选船列表页面通过 OCR
识别所有可见舰船名并直接点击目标舰船。

与普通换船的差异
---------------
- 普通换船: 点击搜索框 → 输入舰船名 → 等待筛选结果 → 点击第一项
- 决战换船: 直接 OCR 识别选船列表 → 按编辑距离模糊匹配 → 点击目标坐标

这是因为决战选船流程没有搜索框（界面为直接列表展示），
且候选集合相对固定（由配置 level1/level2 决定）。

选船算法（对齐 legacy ``Fleet._set_ships`` / ``Fleet.reorder``）
-----------------------------------------------------------------
1. OCR 识别当前舰队 → 标记 ``ok[i]``（保留 / 需处理）
2. **为缺失舰船寻找** ``ok=False`` 槽位并**直接替换**（含已有不需要的船）
3. 从后往前移除剩余 ``ok=False`` 且有舰船的槽位
4. **位置对齐**：逐槽位检查，不在正确位置的船通过 **滑动拖拽**
   (``_circular_move``) 移到正确槽位 — 对齐 legacy ``circular_move``
5. 验证结果，失败则重试（默认最多 2 次）
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.constants import SHIPNAMES
from autowsgr.infra.logger import get_logger
from autowsgr.ui.battle.constants import CLICK_SHIP_SLOT
from autowsgr.ui.battle.preparation import BattlePreparationPage
from autowsgr.ui.choose_ship_page import ChooseShipPage
from autowsgr.vision.ocr import _fuzzy_match


if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

    from autowsgr.context import GameContext
    from autowsgr.infra import DecisiveConfig
    from autowsgr.vision import OCREngine


_log = get_logger('ui.decisive')

# ═══════════════════════════════════════════════════════════════════════════════
# 内部常量
# ═══════════════════════════════════════════════════════════════════════════════

# 出征准备页下方舰船名称标签横条的 Y 范围（相对坐标，与分辨率无关）。
# 实测 1280×720 截图：舰船名字中心 y ≈ 447，故取 y ∈ [435, 462]
# → relative Y ∈ (435/720, 462/720) ≈ (0.604, 0.642)
_NAME_STRIP_Y1: float = 435 / 720
_NAME_STRIP_Y2: float = 462 / 720

# 6 个舰船槽位对应的 X 中心相对坐标 (与 CLICK_SHIP_SLOT 一致)
_SLOT_X_CENTERS: tuple[float, ...] = (0.1146, 0.2292, 0.3438, 0.4583, 0.5729, 0.6875)

# 选船 OCR 最大重试次数（每次失败后向上滚动列表）
_OCR_MAX_ATTEMPTS: int = 3

# 滚动参数（向上翻页）
_SCROLL_FROM_Y: float = 0.55
_SCROLL_TO_Y: float = 0.30

# 舰船名模糊匹配编辑距离阈值
_SHIP_FUZZY_THRESHOLD: int = 2

# 等待选船页面出现的超时 (秒)
_CHOOSE_PAGE_TIMEOUT: float = 5.0

# change_fleet 最大重试次数（对齐 legacy Fleet.set_ship 的 max_retries=2）
_MAX_SET_RETRIES: int = 2


# ═══════════════════════════════════════════════════════════════════════════════
# 页面控制器
# ═══════════════════════════════════════════════════════════════════════════════


class DecisiveBattlePreparationPage(BattlePreparationPage):
    """决战出征准备页面控制器（无搜索框换船版）。

    Parameters
    ----------
    ctrl:
        Android 设备控制器。
    config:
        决战配置。
    ocr:
        OCR 引擎（必须提供，换船时依赖 OCR）。
    """

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
        ocr: OCREngine | None = None,
    ) -> None:
        super().__init__(ctx, ocr)
        # 收窄父类 _ocr 类型：决战版本必须有 OCR 引擎
        self._ocr: OCREngine = ocr or ctx.ocr  # type: ignore[assignment]
        self._config = config

    # ══════════════════════════════════════════════════════════════════════════
    # 当前舰队检测
    # ══════════════════════════════════════════════════════════════════════════

    def detect_fleet(self, screen: np.ndarray | None = None) -> list[str | None]:
        """OCR 识别出征准备页面当前 6 个槽位的舰船名。

        读取屏幕底部舰船名称横条 (Y ≈ 0.80–0.85) 中的各块文字，
        按 X 坐标对应到槽位 0–5。

        Parameters
        ----------
        screen:
            截图 (H×W×3, RGB)；``None`` 时自动截图。

        Returns
        -------
        list[str | None]
            长度为 6 的列表，槽位未占用时为 ``None``。
        """
        if screen is None:
            screen = self._ctrl.screenshot()

        h, w = screen.shape[:2]
        y1 = int(_NAME_STRIP_Y1 * h)
        y2 = int(_NAME_STRIP_Y2 * h)
        strip = screen[y1:y2, :]

        results = self._ocr.recognize(strip)
        ships: list[str | None] = [None] * 6

        for r in results:
            text = r.text.strip()
            if not text or r.bbox is None:
                continue
            matched = _fuzzy_match(text, SHIPNAMES, _SHIP_FUZZY_THRESHOLD)
            if matched is None:
                continue
            # 根据 bbox X 中心确定归属槽位（就近原则）
            cx_rel = (r.bbox[0] + r.bbox[2]) / 2 / w
            slot = min(range(6), key=lambda i, cx=cx_rel: abs(_SLOT_X_CENTERS[i] - cx))
            ships[slot] = matched
            _log.debug("[决战准备] 槽位 {} OCR → '{}'", slot, matched)

        _log.info('[决战准备] 当前舰队: {}', ships)
        return ships

    # ══════════════════════════════════════════════════════════════════════════
    # 舰队验证
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _validate_fleet(
        current: list[str | None],
        desired: list[str | None],
    ) -> bool:
        """验证当前舰队是否已满足目标（**逐槽位精确比对**）。

        Parameters
        ----------
        current:
            OCR 识别到的当前 6 槽位舰船名（``None`` 为空）。
        desired:
            目标 6 槽位舰船名列表（``None`` 为空）。

        Returns
        -------
        bool
            ``True`` 表示每个槽位的舰船都与目标一致。
        """
        for i in range(6):
            c = current[i]
            d = desired[i]
            if d is None:
                continue  # 目标留空的槽位不做要求
            if c != d:
                return False
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # 覆盖 change_fleet — 对齐 legacy _set_ships 三步算法 + 重试
    # ══════════════════════════════════════════════════════════════════════════

    def change_fleet(
        self,
        fleet_id: int | None,
        ship_names: Sequence[str | None],
    ) -> bool:
        """更换决战舰队编成（位置敏感版）。

        **两步算法**（对齐 legacy ``Fleet._set_ships`` + ``Fleet.reorder``）：

        1. **成员对齐** (``_set_ships``) — 确保目标中每艘船都在舰队内：
           - 标记 ``ok[i]``：当前槽位舰船在目标集合中则保留。
           - 对目标中不在舰队的舰船，取第一个 ``ok=False`` 槽位，
             通过选船页替换。
           - 从后往前移除剩余 ``ok=False`` 且有舰船的槽位。
        2. **位置对齐** (``_reorder``) — 逐槽位检查，不在正确位置的
           船通过 **滑动拖拽** (``_circular_move``) 移至正确槽位。

        失败时自动重试（最多 ``_MAX_SET_RETRIES`` 次），每次前重新 OCR 状态。

        Parameters
        ----------
        fleet_id:
            舰队编号 (2–4)；``None`` 代表不指定舰队。1 队不支持更换。
        ship_names:
            目标舰船名列表 (按槽位 0–5 顺序)；``None``/``""`` 表示留空。

        Returns
        -------
        bool
            ``True`` 表示最终验证通过，``False`` 表示全部重试失败。
        """
        if fleet_id == 1:
            raise ValueError('不支持更换 1 队舰船编成')

        names: list[str | None] = [(n or None) for n in list(ship_names)[:6]]
        names += [None] * (6 - len(names))
        _log.info('[决战准备] 目标编成: {}', names)

        for attempt in range(_MAX_SET_RETRIES + 1):
            # ── 1. 检测当前舰队 ──────────────────────────────────────────
            current = self.detect_fleet()

            # ── 前置短路：已满足则无需任何操作 ──────────────────────────
            if self._validate_fleet(current, names):
                _log.info('[决战准备] 舰队已满足目标，跳过换船')
                return True

            desired_set: set[str] = {n for n in names if n is not None}

            # ── 2. 成员对齐：确保目标船都在队中 ─────────────────────────
            ok: list[bool] = [False] * 6
            for i in range(6):
                if current[i] is not None and current[i] in desired_set:
                    ok[i] = True

            for name in names:
                if name is None:
                    continue
                if name in current:
                    continue
                slot = next((i for i in range(6) if not ok[i]), None)
                if slot is None:
                    _log.warning("[决战准备] 无可用槽位放 '{}'，跳过", name)
                    continue
                occupied = current[slot] is not None
                _log.info(
                    "[决战准备] 成员对齐: 槽位 {} ← '{}' (原: '{}')",
                    slot,
                    name,
                    current[slot],
                )
                self._change_single_ship(slot, name, slot_occupied=occupied)
                current[slot] = name
                ok[slot] = True
                time.sleep(0.3)

            for i in range(5, -1, -1):
                if not ok[i] and current[i] is not None:
                    _log.info("[决战准备] 移除槽位 {} 的 '{}'", i, current[i])
                    self._change_single_ship(i, None, slot_occupied=True)
                    current[i] = None
                    time.sleep(0.3)

            # ── 3. 位置对齐：通过滑动拖拽将每艘船移到正确槽位 ──────────
            #    重新 OCR 获取最新状态后，用 circular_move 对齐 legacy reorder
            current = self.detect_fleet()
            self._reorder(current, names)

            # ── 4. 验证结果 ──────────────────────────────────────────────
            current = self.detect_fleet()
            if self._validate_fleet(current, names):
                _log.info('[决战准备] 编成更换完成: {}', current)
                return True

            if attempt < _MAX_SET_RETRIES:
                _log.warning(
                    '[决战准备] 第 {}/{} 次验证失败，重试...',
                    attempt + 1,
                    _MAX_SET_RETRIES + 1,
                )
                time.sleep(0.5)
            else:
                _log.error(
                    '[决战准备] 舰队设置在 {} 次尝试后仍然失败，当前: {}',
                    _MAX_SET_RETRIES + 1,
                    current,
                )

        return False

    # ══════════════════════════════════════════════════════════════════════════
    # 位置对齐 — 对齐 legacy Fleet.reorder / Fleet.circular_move
    # ══════════════════════════════════════════════════════════════════════════

    def _reorder(
        self,
        current: list[str | None],
        desired: list[str | None],
    ) -> None:
        """通过滑动将舰船移至目标位置 (对齐 legacy ``Fleet.reorder``)。

        从左到右逐槽位检查，若当前位置不是目标船则找到目标船所在
        槽位，通过 ``_circular_move`` 滑动到正确位置。

        Parameters
        ----------
        current:
            **变参**: 当前 6 槽位舰船名，本方法会就地修改。
        desired:
            目标 6 槽位舰船名。
        """
        for i in range(6):
            target = desired[i]
            if target is None:
                break  # 对齐 legacy: 遇到空位即停止
            if current[i] == target:
                continue
            try:
                src = current.index(target)
            except ValueError:
                _log.warning(
                    "[决战准备] 位置对齐: '{}' 不在当前舰队中, 跳过",
                    target,
                )
                continue
            _log.info(
                "[决战准备] 位置对齐: 槽位 {} ← '{}' (从槽位 {})",
                i,
                target,
                src,
            )
            self._circular_move(src, i, current)

    def _circular_move(
        self,
        src: int,
        dst: int,
        current: list[str | None],
    ) -> None:
        """滑动将舰船从 *src* 槽位移至 *dst* 槽位 (对齐 legacy ``Fleet.circular_move``)。

        游戏行为: 拖拽 src 到 dst 后，src 与 dst 之间的舰船做循环位移。

        Parameters
        ----------
        src:
            源槽位 (0–5)。
        dst:
            目标槽位 (0–5)。
        current:
            **变参**: 当前 6 槽位舰船名，就地更新以反映移动后状态。
        """
        if src == dst:
            return
        sx, sy = CLICK_SHIP_SLOT[src]
        dx, dy = CLICK_SHIP_SLOT[dst]
        self._ctrl.swipe(sx, sy, dx, dy, duration=0.5)

        # 更新本地追踪（circular shift，对齐 legacy）
        ship = current.pop(src)
        current.insert(dst, ship)
        time.sleep(0.5)

    # ══════════════════════════════════════════════════════════════════════════
    # 覆盖 _change_single_ship — 无搜索框 OCR 版本
    # ══════════════════════════════════════════════════════════════════════════

    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        slot_occupied: bool = True,
    ) -> None:
        """决战专用单槽换船：不输入搜索框，直接 OCR 列表并点击。

        流程
        ----
        1. 点击舰船槽位，等待选船页面加载
        2. 若 ``name`` 为 ``None``：点击「移除」按钮
        3. 否则：OCR 左侧选船列表（多次重试+滚动）→ 模糊匹配 → 点击

        Parameters
        ----------
        slot:
            槽位编号 (0–5)。
        name:
            目标舰船名；``None`` 表示移除该槽位舰船。
        slot_occupied:
            当前槽位是否有舰船（用于跳过空移除）。

        Raises
        ------
        不抛异常：找不到目标舰船时记录错误并关闭选船页面。
        """
        if name is None and not slot_occupied:
            return

        self.click_ship_slot(slot)

        # 等待选船页面就绪
        deadline = time.monotonic() + _CHOOSE_PAGE_TIMEOUT
        screen = self._ctrl.screenshot()
        while not ChooseShipPage.is_current_page(screen):
            if time.monotonic() >= deadline:
                _log.error("[决战准备] 等待选船页面超时 (槽位={}, 目标='{}')", slot, name)
                return
            time.sleep(0.05)
            screen = self._ctrl.screenshot()

        choose_page = ChooseShipPage(self._ctx)

        if name is None:
            # ── 移除 ──────────────────────────────────────────────────────
            _log.info('[决战准备] 移除槽位 {} 的舰船', slot)
            time.sleep(0.8)
            choose_page.click_remove()
            return

        # ── 换船：OCR 识别列表并点击 ─────────────────────────────────────
        found = self._click_ship_in_list(name)
        if not found:
            _log.error(
                "[决战准备] 未在选船列表中找到 '{}'，放弃换船（槽位 {}）",
                name,
                slot,
            )
            # TODO: 细化错误类型
            raise RuntimeError(f"未找到目标舰船 '{name}'")

    # ══════════════════════════════════════════════════════════════════════════
    # 内部辅助
    # ══════════════════════════════════════════════════════════════════════════

    def _click_ship_in_list(self, name: str) -> bool:
        """在选船列表页使用 DLL 定位 + OCR 识别舰船名并点击目标。

        复用 :func:`~autowsgr.ui.decisive.fleet_ocr.locate_ship_rows` 做
        DLL 行定位 + 逐行 OCR，在结果中查找 ``name`` 并点击其行中心。

        最多重试 :data:`_OCR_MAX_ATTEMPTS` 次，每次失败后向上滚动列表。

        Parameters
        ----------
        name:
            目标舰船名（精确名称，来自候选列表）。

        Returns
        -------
        bool
            ``True`` 表示已成功点击目标；``False`` 表示全程未找到。
        """
        import autowsgr.ui.decisive.fleet_ocr as _fleet_ocr

        for attempt in range(_OCR_MAX_ATTEMPTS):
            screen = self._ctrl.screenshot()

            hits = _fleet_ocr.locate_ship_rows(self._ocr, screen)

            for matched, cx, cy in hits:
                if matched != name:
                    continue
                _log.info(
                    "[决战准备] DLL+OCR → '{}' (第 {}/{} 次)，点击 ({:.3f}, {:.3f})",
                    name,
                    attempt + 1,
                    _OCR_MAX_ATTEMPTS,
                    cx,
                    cy,
                )
                time.sleep(1.0)
                self._ctrl.click(cx, cy)
                return True

            _log.warning(
                "[决战准备] 选船列表未匹配到 '{}' (第 {}/{} 次)，向上滚动",
                name,
                attempt + 1,
                _OCR_MAX_ATTEMPTS,
            )
            if attempt < _OCR_MAX_ATTEMPTS - 1:
                self._ctrl.swipe(0.4, _SCROLL_FROM_Y, 0.4, _SCROLL_TO_Y, duration=0.4)
                time.sleep(0.5)

        return False
