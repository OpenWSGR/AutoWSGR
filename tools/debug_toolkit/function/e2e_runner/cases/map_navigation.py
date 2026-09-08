"""Map-only navigation stress case.

Runs one shuffled set of chapters 1-9 and maps 1-4 for several rounds. It
never enters sortie preparation or starts combat; every target is verified by
the map title OCR after navigation.
"""

from __future__ import annotations

import random
import time
from typing import Any


DESC = '地图导航压力测试: 1-9章×1-4地图, 只导航不战斗'


def add_arguments(parser: Any) -> None:
    """Define case-specific arguments."""
    parser.add_argument('--rounds', type=int, default=3, help='轮数 (默认 3)')
    parser.add_argument('--seed', type=int, default=None, help='随机排列种子 (默认随机)')


def _navigate_target(page: Any, ctx: Any, chapter: int, map_num: int) -> None:
    """Navigate to one map without entering sortie preparation."""
    reached = page.navigate_to_chapter(chapter)
    if reached != chapter:
        raise RuntimeError(f'章节导航结果错误: 目标={chapter}, 实际={reached}')

    page.navigate_to_map(map_num)
    info = page.recognize_map(ctx.ctrl.screenshot(), ctx.ocr)
    if info is None:
        raise RuntimeError(f'地图标题 OCR 失败: 目标={chapter}-{map_num}')
    if (info.chapter, info.map_num) != (chapter, map_num):
        raise RuntimeError(
            f'地图标题不匹配: 目标={chapter}-{map_num}, 实际={info.chapter}-{info.map_num}'
        )


def run(rt: Any) -> bool:
    """Run three rounds of shuffled map-only navigation."""
    from autowsgr.ops.navigate import goto_page
    from autowsgr.types import PageName
    from autowsgr.ui.map.data import MapPanel
    from autowsgr.ui.map.page import MapPage

    if rt.args.rounds <= 0:
        raise ValueError('--rounds 必须大于 0')

    seed = rt.args.seed if rt.args.seed is not None else random.SystemRandom().randrange(1 << 31)
    targets = [(chapter, map_num) for chapter in range(1, 10) for map_num in range(1, 5)]
    random.Random(seed).shuffle(targets)
    total = len(targets) * rt.args.rounds
    rt.note(f'随机种子: {seed}; 每轮 {len(targets)} 个目标; 总计 {total} 次导航')
    rt.note(f'顺序: {targets}')

    ctx = rt.ctx
    if rt.action('进入地图页面', goto_page, ctx, PageName.MAP) is rt.FAILED:
        return False

    page = MapPage(ctx)
    if rt.action('切换到出征面板', page.ensure_panel, MapPanel.SORTIE) is rt.FAILED:
        return False
    time.sleep(1.5)

    completed = 0
    for round_index in range(1, rt.args.rounds + 1):
        rt.note(f'开始第 {round_index}/{rt.args.rounds} 轮')
        for index, (chapter, map_num) in enumerate(targets, 1):
            label = f'第{round_index}轮 {index}/{len(targets)}: 导航 {chapter}-{map_num}'
            result = rt.action(
                label,
                _navigate_target,
                page,
                ctx,
                chapter,
                map_num,
            )
            if result is rt.FAILED:
                return False
            completed += 1

    return rt.check('完成全部地图导航', lambda: completed == total)
