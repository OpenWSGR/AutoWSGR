"""UI 页面注册中心。

提供页面注册与识别功能:

- **register_page** - 注册页面识别函数
- **get_current_page** - 遍历注册表识别当前截图
- **get_registered_pages** - 列出所有已注册页面

导航 / 等待工具函数已迁移至 :mod:`autowsgr.ui.utils`，
此处保留兼容性再导出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.infra.logger import get_logger
from autowsgr.ui.utils import (
    DEFAULT_NAV_CONFIG,
    NavConfig,
    NavigationError,
    click_and_wait_for_page,
    click_and_wait_leave_page,
    confirm_operation,
    wait_for_page,
    wait_leave_page,
)
from autowsgr.vision.page_match import PageMatch


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np


_log = get_logger('ui')

# ---------------------------------------------------------------------------
# 页面注册中心
# ---------------------------------------------------------------------------

_PAGE_REGISTRY: dict[str, Callable[[np.ndarray], PageMatch | bool]] = {}

_OVERLAY_PAGES: set[str] = set()
"""覆盖型页面名集合 (抽屉/浮层)。

这类页面**不遮挡底页的识别元素** (如侧边栏是左侧抽屉, 主页面签名元素在
右侧): 打开时底页签名仍会命中, 且分数往往更高 (主页面 0.988 vs 侧边栏
~0.86)。纯分数排序会把"侧边栏开着"误判为纯主页面, 导致导航在"已到达
侧边栏"与"当前是主页面"之间震荡 — 反复点击切换按钮把侧边栏开了又关,
等待超时 (实机 2026-08-16: 船坞满自动解装的 MAIN→SIDEBAR 死循环)。"""


def register_page(
    name: str,
    checker: Callable[[np.ndarray], PageMatch | bool],
    *,
    overlay: bool = False,
) -> None:
    """注册页面识别函数。

    checker 宜返回 :class:`~autowsgr.vision.page_match.PageMatch`(携带 score,
    供候选集排序);兼容旧式返回 ``bool`` 的识别器(自动归一化:True→1.0, False→0.0)。

    Parameters
    ----------
    name:
        页面名 (PageName 或纯 str)。
    checker:
        页面识别函数。
    overlay:
        是否为覆盖型页面 (抽屉/浮层, 见 :data:`_OVERLAY_PAGES`)。
        覆盖型页面命中时优先于底页返回 (z-order 优先于分数)。
    """
    # Python 3.13+ 中 StrEnum 的 str()/format() 返回 'ClassName.MEMBER' 而非值，
    # 显式提取 .value 确保 key 始终为纯 str，避免日志和比较中出现意外格式。
    key: str = name.value if hasattr(name, 'value') else name
    if key in _PAGE_REGISTRY:
        _log.warning("[UI] 页面 '{}' 已注册，将覆盖", key)
    _PAGE_REGISTRY[key] = checker
    if overlay:
        _OVERLAY_PAGES.add(key)
    else:
        _OVERLAY_PAGES.discard(key)
    # _log.debug("[UI] 注册页面: {}", key)


def _normalize_match(name: str, result: object) -> PageMatch:
    """把识别器返回值归一化为 :class:`PageMatch`。

    兼容三种返回:

    - :class:`PageMatch` —— 直接采用(以注册名覆盖 ``result.name``,防漂移)
    - ``bool`` —— 旧式布尔识别器,True → score=1.0, False → 0.0
    - 其他(如 :class:`~autowsgr.vision.PixelMatchResult`)——
      取 ``.matched`` 与 ``.score``/``.ratio``/``.confidence`` 之一
    """
    if isinstance(result, PageMatch):
        return (
            result
            if result.name == name
            else PageMatch(
                name=name,
                matched=result.matched,
                score=result.score,
            )
        )
    if isinstance(result, bool):
        return PageMatch(name=name, matched=result, score=1.0 if result else 0.0)
    matched = bool(getattr(result, 'matched', False))
    raw = getattr(result, 'score', None)
    if raw is None:
        raw = getattr(result, 'ratio', None)
    if raw is None:
        raw = getattr(result, 'confidence', None)
    score = float(raw) if raw is not None else (1.0 if matched else 0.0)
    return PageMatch(name=name, matched=matched, score=score)


def get_current_page(
    screen: np.ndarray,
    candidates: set[str] | None = None,
) -> str | None:
    """识别截图对应的页面名称,无匹配返回 ``None``。

    覆盖型页面 (overlay) 命中时优先于底页返回 — 用户可见/可操作的是覆盖层,
    底页签名同时命中属于预期 (不遮挡)。非覆盖命中集内按 ``score`` 降序取
    最高分(替代旧的"首次匹配即胜"); 分数相同者保持注册(候选)顺序。每个
    识别器返回 :class:`~autowsgr.vision.page_match.PageMatch`,score 归一自
    像素 ratio / 模板 confidence / tabbed 覆盖度。

    Parameters
    ----------
    screen:
        截图 (HxWx3, RGB)。
    candidates:
        候选页面名集合。给出时只评估候选页 —— 导航时可利用"当前页 + 可达页"
        上下文约束,大幅降低不特异签名(如决战页深色背景点)误命中无关页的风险。
        为 ``None`` 时评估全部注册页。
    """
    # 按注册顺序遍历候选(而非候选 set 的任意顺序):同分时稳定排序保持注册顺序,
    # 让旧的"注册顺序优先级"(如 EVENT_MAP 排在 DECISIVE_BATTLE 前)自然融入排序语义。
    reg_order: list[str] = list(_PAGE_REGISTRY.keys())
    if candidates is not None:
        names = [n for n in reg_order if n in candidates]
    else:
        names = reg_order
    hits: list[PageMatch] = []
    failed: list[str] = []
    for name in names:
        checker = _PAGE_REGISTRY.get(name)
        if checker is None:
            continue
        try:
            pm = _normalize_match(name, checker(screen))
        except Exception:
            _log.opt(exception=True).warning("[UI] 页面 '{}' 识别器异常", name)
            failed.append(name)
            continue
        if pm.matched:
            hits.append(pm)

    if hits:
        # 覆盖型优先 (z-order): 侧边栏开着时主页面也命中且分更高, 但当前页是侧边栏
        overlay_hits = [m for m in hits if m.name in _OVERLAY_PAGES]
        pool = overlay_hits or hits
        # 稳定排序:分数降序,同分保持候选顺序
        pool.sort(key=lambda m: m.score, reverse=True)
        best = pool[0]
        _log.debug(
            '[UI] 当前页面: {} (score={:.3f}, 候选 {} / 命中 {})',
            best.name,
            best.score,
            len(names),
            len(hits),
        )
        return best.name

    if failed:
        _log.warning(
            '[UI] 无匹配页面，且以下识别器抛异常: {} (评估 {} 个候选)',
            failed,
            len(names),
        )
    else:
        _log.debug('[UI] 当前页面: 无匹配 (评估 {} 个候选)', len(names))
    return None


def get_registered_pages() -> list[str]:
    """返回所有已注册的页面名称列表。"""
    return list(_PAGE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# 兼容性再导出 - 所有从 page 导入的旧路径继续工作
# ---------------------------------------------------------------------------
__all__ = [
    'DEFAULT_NAV_CONFIG',
    'NavConfig',
    'NavigationError',
    'click_and_wait_for_page',
    'click_and_wait_leave_page',
    'confirm_operation',
    'get_current_page',
    'get_registered_pages',
    'register_page',
    'wait_for_page',
    'wait_leave_page',
]
