"""页面识别诊断工具。

连接模拟器截一张图, 判断当前位于哪个页面, 并列出标签页识别中
5 个候选页面各自的覆盖度 (概率), 用于排查「识别成别的页面」类问题。

使用方式::

    # 连接模拟器, 截图后识别
    python tools/detect_page.py

    # 指定配置文件
    python tools/detect_page.py -c usersettings.yaml

    # 分析已有图片 (跳过连接)
    python tools/detect_page.py -i logs/debug_screenshot/screenshot.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_BAR_WIDTH = 28
_THRESHOLD = 0.6

_TAB_LABELS: dict[str, tuple[str, ...]] = {
    '地图页面': ('出征', '演习', '远征', '战役', '决战'),
    '建造页面': ('建造', '解体', '开发', '废弃'),
    '强化页面': ('强化', '改修', '技能'),
    '任务页面': ('任务',),
    '好友页面': ('好友', '访问', '搜索', '申请'),
}
"""各标签页的标签文字 — 与 :mod:`autowsgr.ui.tabbed_page` 模块文档里的对应表一致。"""


def capture_screenshot(config_path: str) -> np.ndarray:
    """连接模拟器并截图。"""
    from autowsgr.scheduler import Launcher

    print('连接模拟器...')
    launcher = Launcher(config_path)
    launcher.load_config()
    launcher.connect()
    ctx = launcher.build_context()
    print('截图...')
    return ctx.ctrl.screenshot()


def _bar(score: float) -> str:
    filled = round(min(max(score, 0.0), 1.0) * _BAR_WIDTH)
    return '#' * filled + '.' * (_BAR_WIDTH - filled)


def _page_name(page_type: object) -> str:
    """取 ``TabbedPageType`` 的中文页面名 (其 value 是 PageName 枚举)。"""
    return str(page_type.value.value)


def report_tabbed(screen: np.ndarray) -> None:
    """打印标签栏探测结果与 5 个候选页面的覆盖度。"""
    from autowsgr.ui import tabbed_page as tp

    tabbed = tp.is_tabbed_page(screen)
    active = tp.get_active_tab_index(screen)

    print('\n=== 标签栏探测 ===')
    print(f'  是否为标签页: {"是" if tabbed else "否"}')
    print(f'  激活标签索引: {"无法确定" if active is None else active}')

    scores = tp.score_all_pages(screen)
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    if active is not None and ranked:
        labels = _TAB_LABELS.get(_page_name(ranked[0][0]), ())
        if 0 <= active < len(labels):
            print(f'  激活标签名称: {labels[active]}')

    print(f'\n=== 页面类型覆盖度 (共用 {tp._ref_width(tp._CROP_X_MAP)} px 条带) ===')
    for page_type, score in ranked:
        mark = '命中' if tabbed and score > _THRESHOLD else ''
        print(f'  {_page_name(page_type):6s} {score:.4f}  {_bar(score)}  {mark}')
    print(f'  阈值 {_THRESHOLD:.2f}: 低于该值的页面不会被认定')


def report_verdict(screen: np.ndarray) -> None:
    """打印两层识别结论。"""
    from autowsgr.ui.page import get_current_page
    from autowsgr.ui.tabbed_page import identify_page_type

    print('\n=== 结论 ===')
    tabbed_page = identify_page_type(screen)
    if tabbed_page is None:
        print('  标签页判定: 无法识别 (非标签页, 或最高覆盖度未达阈值)')
    else:
        print(f'  标签页判定: {_page_name(tabbed_page)}')

    page = get_current_page(screen)
    print(f'  页面注册中心: {page if page is not None else "无匹配"}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='判断当前位于哪个页面, 并列出标签页候选的覆盖度',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-c', '--config', default='usersettings.yaml', help='配置文件路径')
    parser.add_argument('-i', '--image', help='从本地图片加载 (跳过连接模拟器)')
    args = parser.parse_args()

    if args.image:
        # 用 imdecode 而非 imread: 截图文件名常含中文, imread 在 Windows 上会失败
        buf = np.fromfile(args.image, dtype=np.uint8)
        bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR) if buf.size else None
        if bgr is None:
            print(f'错误: 无法加载图片: {args.image}')
            sys.exit(1)
        screen = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        print(f'从图片加载: {args.image}')
    else:
        screen = capture_screenshot(args.config)

    print(f'截图尺寸: {screen.shape[1]}x{screen.shape[0]}')
    report_tabbed(screen)
    report_verdict(screen)


if __name__ == '__main__':
    main()
