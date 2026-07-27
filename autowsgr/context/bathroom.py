"""浴室修理槽位状态 — 跟踪各修理槽的释放时间。

移植自 classic ``port/common.py::BathRoom`` 的状态机, 但**不移植其逐槽像素
扫描** (classic 在 ``task_runner.py`` 用硬编码坐标 + 「快速修理」OCR 文字
逐个点开槽位读取剩余时间)。dev 浴室页面用像素签名模型, 坐标与判定方式
不同, 逐槽扫描无法直接复用且无法离线验证。

替代方案 (等价空位调度)
-----------------------
``available_time`` 仅跟踪**本脚本派出的修理**: :meth:`BathRoom.occupy` 在
成功派修后记录该槽释放时间。配合 ``BathPage`` 选择修理 overlay 的点击反馈
(``_try_wait_overlay_close``: overlay 关闭 = 修成功 / 未关 = 浴场满) 实现:

- 有空闲槽才派修 (:meth:`is_available`);
- 跟踪已派修理的进度 (释放时间戳自然到期 = 槽回收);
- 浴场满则 :meth:`mark_unknown` 退避, 下次触发重试。

启动时状态未知 (``None``), 首次触发尝试派修即可恢复。纯内存不持久化
(与 classic 一致)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class BathRoom:
    """浴室修理槽位状态机。

    Attributes
    ----------
    available_time:
        每个修理槽的绝对释放时间戳 (``time.time()`` 基); ``None`` 表示状态
        未知 (需尝试派修以重建)。元素值 ``<= now`` 表示该槽空闲。
    slot_count:
        修理槽总数 (来自 ``config.bathroom_count``), 用于初始化槽位数。
    """

    available_time: list[float] | None = None
    slot_count: int = 2

    def _ensure_initialized(self) -> None:
        """首次使用时按 slot_count 初始化为全空闲。"""
        if self.available_time is None:
            self.available_time = [0.0] * max(1, self.slot_count)

    def is_available(self) -> bool:
        """是否有空闲槽位。状态未知时返回 True (允许尝试派修)。"""
        if self.available_time is None:
            return True
        return self.get_waiting_time() == 0.0

    def get_waiting_time(self) -> float:
        """最近一个槽释放还需等待的秒数; ``0.0`` 表示已有空位。

        状态未知 (``None``) 返回 ``0.0``。
        """
        if self.available_time is None:
            return 0.0
        now = time.time()
        waiting = float('inf')
        for release in self.available_time:
            if now >= release:
                return 0.0
            waiting = min(waiting, release - now)
        return waiting

    def occupy(self, repair_seconds: int) -> None:
        """占用一个空闲槽: 记录其释放时间 = ``now + repair_seconds``。

        若状态未初始化会先初始化; 若无空闲槽则静默忽略 (调用方应先判
        :meth:`is_available`)。
        """
        self._ensure_initialized()
        assert self.available_time is not None
        if repair_seconds <= 0:
            return
        now = time.time()
        for i, release in enumerate(self.available_time):
            if now >= release:
                self.available_time[i] = now + repair_seconds
                return

    def mark_unknown(self) -> None:
        """标记状态未知, 强制下次触发重新尝试派修。"""
        self.available_time = None
