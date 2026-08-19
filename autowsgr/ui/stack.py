"""UI 导航栈 — 页面来路追踪。

栈有两个消费者:

1. **识别候选剪枝** — :meth:`UIStack.candidates` 把全注册表盲扫描收缩到
   "当前页 + 其邻域 + 父页 + 目标页及其邻域", 降低不特异签名误命中风险。
   相比纯邻域机制额外纳入 ``{parent}``, 覆盖"识别发生在回退动作之后"的
   时序, 以及 CHOOSE_SHIP 这类导航图中无入边的叶子页 (来路只存在于栈中)。
2. **go_back 期望父页** — 回退前从栈 ``pop()`` 得到期望落点, 供正向验证。

导航循环每步识别后调用 :meth:`UIStack.observe` 对账, 实际页面与栈预测
不符时置 ``drifted``, 由 :meth:`UIStack.resync` 全量识别重建。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.navigation import neighbors


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.types import PageName


_log = get_logger('ui')

OVERLAY_CANDIDATES: set[str] = set()
"""任意导航步后都可能叠加出现、固定纳入识别候选的页面名集合。

当前为空 —— 主页面浮层 (新闻/签到/预约/提督信息) 已被 MAIN 识别器吸收,
网络错误等全局弹窗页留待后续填充。
"""


def _page_name(page: str | PageName) -> str:
    """归一化页面名 (兼容 :class:`PageName` 与纯 ``str``)。"""
    # Python 3.13+ 中 StrEnum 的 str()/format() 返回 'ClassName.MEMBER',
    # 显式取 .value 确保始终为纯 str。
    return page.value if hasattr(page, 'value') else page


@dataclass(slots=True)
class _StackFrame:
    """栈内单帧:页面名 + 留存截图 (可选)。"""

    page: str
    screen: np.ndarray | None = None


class UIStack:
    """UI 导航栈:页面来路追踪。

    不持有 :class:`~autowsgr.context.GameContext` (避免循环依赖),
    识别对账所需的页面名由调用方传入。线程锁为防御性持有
    (ops 层单线程是既有假设)。

    Parameters
    ----------
    max_depth:
        栈最大深度, 超出时丢弃最老帧 (保底保留根帧)。
    keep_frames:
        留存截图的帧数上限 —— 仅最近 N 帧保留 ``screen``,
        更早帧只留页面名 (内存 ~4MB 上限)。留存帧目前只存不消费,
        为后续浮层比对预留参照帧。
    """

    def __init__(self, *, max_depth: int = 8, keep_frames: int = 2) -> None:
        self._frames: list[_StackFrame] = []
        self._max_depth = max_depth
        self._keep_frames = keep_frames
        self._drifted = False
        self._lock = threading.Lock()

    # ── 栈操作 ──────────────────────────────────────────────────────────

    def push(self, page: str | PageName, *, screen: np.ndarray | None = None) -> None:
        """进入新页面 (声明意图; 下一轮识别的 ``observe`` 会纠正)。"""
        name = _page_name(page)
        with self._lock:
            if self._frames and self._frames[-1].page == name:
                # 同页重入 (如浮层开合) 刷新留存帧, 不叠重复帧
                self._frames[-1].screen = screen
            else:
                self._frames.append(_StackFrame(name, screen))
            self._trim()

    def pop(self) -> str | None:
        """弹出栈顶并返回其页面名; 空栈返回 ``None``。

        go_back 的期望父页来源: pop 后的新栈顶即期望落点。
        """
        with self._lock:
            if not self._frames:
                return None
            return self._frames.pop().page

    def replace(self, page: str | PageName, *, screen: np.ndarray | None = None) -> None:
        """替换栈顶 (同层 tab 切换 / 人工识别校正), 并清除漂移标记。"""
        name = _page_name(page)
        with self._lock:
            self._frames[-1:] = [_StackFrame(name, screen)]
            self._drifted = False
            self._trim()

    def reset(self, page: str | PageName, *, screen: np.ndarray | None = None) -> None:
        """清空栈并以 *page* 重建单帧根 (:meth:`resync` 使用)。"""
        name = _page_name(page)
        with self._lock:
            self._frames = [_StackFrame(name, screen)]
            self._drifted = False

    def _trim(self) -> None:
        """深度裁剪 + 留存帧淘汰。调用方须持锁。"""
        if len(self._frames) > self._max_depth:
            del self._frames[: len(self._frames) - self._max_depth]
        # 仅保留最近 keep_frames 帧的留存截图
        for i, frame in enumerate(self._frames):
            if len(self._frames) - i > self._keep_frames:
                frame.screen = None

    # ── 查询 ────────────────────────────────────────────────────────────

    @property
    def current(self) -> str | None:
        """栈顶页面名; 空栈返回 ``None``。"""
        with self._lock:
            return self._frames[-1].page if self._frames else None

    @property
    def parent(self) -> str | None:
        """栈顶的上一页 (来路); 栈深 < 2 返回 ``None``。"""
        with self._lock:
            return self._frames[-2].page if len(self._frames) >= 2 else None

    @property
    def depth(self) -> int:
        """当前栈深。"""
        with self._lock:
            return len(self._frames)

    def pages(self) -> tuple[str, ...]:
        """栈快照 (根 → 栈顶), 调试 / 日志用。"""
        with self._lock:
            return tuple(f.page for f in self._frames)

    @property
    def drifted(self) -> bool:
        """实际页面是否已脱离栈预测范围 (待 :meth:`resync` 重建)。"""
        return self._drifted

    # ── 识别候选 ────────────────────────────────────────────────────────

    def candidates(self, target: str | PageName | None = None) -> set[str]:
        """计算下一轮页面识别的候选集::

            {current} + neighbors(current) + {parent}
            + {target} + neighbors(target) + OVERLAY_CANDIDATES

        空栈且无 *target* 时返回空集 —— 调用方应视为 ``None`` (全量识别)。

        Parameters
        ----------
        target:
            导航目标页 (可选)。
        """
        with self._lock:
            current = self._frames[-1].page if self._frames else None
            parent = self._frames[-2].page if len(self._frames) >= 2 else None

        result: set[str] = set()
        if current is not None:
            result.add(current)
            result |= neighbors(current)
        if parent is not None:
            result.add(parent)
        if target is not None:
            name = _page_name(target)
            result.add(name)
            result |= neighbors(name)
        result |= OVERLAY_CANDIDATES
        return result

    # ── 识别对账 ────────────────────────────────────────────────────────

    def observe(self, identified: str | PageName, *, screen: np.ndarray | None = None) -> str:
        """用识别结果对账栈, 返回对账后的栈顶页面名。

        四个分支 (按序判定)::

            栈空            → push 为根
            == current      → 不动, 刷新留存帧
            == parent       → pop (自然回退)
            ∈ neighbors(current) → push (前进)
            其他            → drifted, 不改栈

        ``parent`` 判定先于 ``neighbors``: 双向边 (如 MAP↔MAIN) 上
        "识别为父页"应理解为回退而非前进, pop 才能正确回收来路。

        Parameters
        ----------
        identified:
            全量 / 候选识别得到的实际页面名。
        screen:
            触发本次识别的截图 (存为留存帧, 可选)。
        """
        name = _page_name(identified)
        with self._lock:
            if not self._frames:
                self._frames = [_StackFrame(name, screen)]
                return name

            current = self._frames[-1].page
            parent = self._frames[-2].page if len(self._frames) >= 2 else None

            if name == current:
                self._frames[-1].screen = screen
                return current

            if parent is not None and name == parent:
                self._frames.pop()
                self._frames[-1].screen = screen
                return name

            if name in neighbors(current):
                self._frames.append(_StackFrame(name, screen))
                self._trim()
                return name

            self._drifted = True
            _log.warning(
                "[UIStack] 漂移: 识别为 '{}', 栈预测 '{}' (栈: {})",
                name,
                current,
                ' → '.join(f.page for f in self._frames),
            )
            return current

    # ── 重建 / 留存帧 ───────────────────────────────────────────────────

    def resync(self, screen: np.ndarray) -> str | None:
        """全量识别 *screen* 并据识别结果重建栈 (单帧根)。

        重建不猜祖先链 —— 来路信息已不可靠, 由后续导航重新积累。
        识别失败时清空栈并返回 ``None``。

        Parameters
        ----------
        screen:
            当前截图。

        Returns
        -------
        str | None
            识别并重建后的根页面名; 识别失败返回 ``None``。
        """
        from autowsgr.ui.page import get_current_page

        identified = get_current_page(screen)
        if identified is None:
            with self._lock:
                self._frames.clear()
                self._drifted = False
            _log.warning('[UIStack] resync: 全量识别失败, 栈已清空')
            return None
        self.reset(identified, screen=screen)
        _log.info('[UIStack] resync: 栈重建为 [{}]', identified)
        return identified

    def snapshot(self, page: str | PageName) -> np.ndarray | None:
        """返回 *page* 最近一次的留存截图; 无留存返回 ``None``。"""
        name = _page_name(page)
        with self._lock:
            for frame in reversed(self._frames):
                if frame.page == name:
                    return frame.screen
        return None
