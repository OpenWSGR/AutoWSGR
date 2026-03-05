"""通用游戏截图 + OCR 调试工具。

连接模拟器，截图并对指定区域执行 OCR，保存所有中间图像。
适用于排查任何页面的 OCR / 像素识别问题。

使用方式::

    # 截图并交互式检查像素 / OCR
    python tools/debug_screenshot.py

    # 指定配置文件
    python tools/debug_screenshot.py -c usersettings.yaml

    # 从已有图片分析
    python tools/debug_screenshot.py -i screenshot.png

    # 对指定区域做 OCR (相对坐标: x1,y1,x2,y2)
    python tools/debug_screenshot.py --roi 0.818,0.81,0.875,0.867

    # 指定 OCR 白名单
    python tools/debug_screenshot.py --roi 0.818,0.81,0.875,0.867 --allowlist "0123456789Ex-"

    # 检查像素签名
    python tools/debug_screenshot.py --check-page decisive_battle

    # 保存到自定义目录
    python tools/debug_screenshot.py -o logs/my_debug
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import cv2


if TYPE_CHECKING:
    import numpy as np


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

DEFAULT_OUTPUT_DIR = Path('logs/debug_screenshot')


def _save(img: np.ndarray, name: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), bgr)
    print(f'  保存: {path}')
    return path


def _crop(screen: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = screen.shape[:2]
    return screen[int(y1 * h) : int(y2 * h), int(x1 * w) : int(x2 * w)].copy()


def _draw_roi(
    screen: np.ndarray,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: tuple[int, int, int] = (255, 0, 0),
    label: str = '',
) -> np.ndarray:
    vis = screen.copy()
    h, w = vis.shape[:2]
    cv2.rectangle(vis, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), color, 2)
    if label:
        cv2.putText(
            vis, label, (int(x1 * w), int(y1 * h) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
        )
    return vis


def _print_pixel_info(screen: np.ndarray, rx: float, ry: float) -> None:
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    if 0 <= px < w and 0 <= py < h:
        r, g, b = screen[py, px]
        print(f'  像素 ({rx:.4f}, {ry:.4f}) → ({px}, {py}) → RGB({r}, {g}, {b})')


def capture_screenshot(config_path: str = 'usersettings.yaml') -> np.ndarray:
    """连接模拟器并截图。"""
    from autowsgr.scheduler import Launcher

    print('连接模拟器...')
    launcher = Launcher(config_path)
    launcher.load_config()
    launcher.connect()
    ctx = launcher.build_context()
    print('截图...')
    return ctx.ctrl.screenshot()


def check_page_signatures(screen: np.ndarray, page_name: str | None = None) -> None:
    """检查当前截图匹配哪些页面签名。"""
    from autowsgr.vision import PixelChecker

    # 收集所有已知的页面签名
    known_pages = {}
    try:
        from autowsgr.ui.decisive.battle_page import PAGE_SIGNATURE as DECISIVE_SIG

        known_pages['decisive_battle'] = DECISIVE_SIG
    except ImportError:
        pass
    try:
        from autowsgr.ui.main_page import PAGE_SIGNATURE as MAIN_SIG

        known_pages['main'] = MAIN_SIG
    except ImportError:
        pass

    print('\n=== 页面签名检测 ===')
    for name, sig in known_pages.items():
        if page_name and name != page_name:
            continue
        result = PixelChecker.check_signature(screen, sig)
        status = '✓ 匹配' if result.matched else '✗ 不匹配'
        print(f'  {name}: {status}')
        if hasattr(result, 'details') and result.details:
            for d in result.details:
                print(
                    f'    ({d.rx:.4f}, {d.ry:.4f}): '
                    f'期望 {d.expected} 实际 {d.actual} '
                    f'距离={d.distance:.1f} {"✓" if d.passed else "✗"}'
                )


def run_ocr_on_roi(
    screen: np.ndarray,
    roi: tuple[float, float, float, float],
    allowlist: str = '',
    out_dir: Path = DEFAULT_OUTPUT_DIR,
) -> None:
    """对指定 ROI 区域执行 OCR 测试。"""
    from autowsgr.vision import EasyOCREngine

    x1, y1, x2, y2 = roi
    cropped = _crop(screen, x1, y1, x2, y2)
    print(f'\nROI: ({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f})')
    print(f'裁切尺寸: {cropped.shape[1]}x{cropped.shape[0]}')

    _save(cropped, 'roi_crop.png', out_dir)
    enlarged = cv2.resize(cropped, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    _save(enlarged, 'roi_crop_4x.png', out_dir)
    vis = _draw_roi(screen, x1, y1, x2, y2, label='ROI')
    _save(vis, 'annotated.png', out_dir)

    print('\n初始化 OCR...')
    ocr = EasyOCREngine.create(gpu=False)

    print('\n=== OCR: 无白名单 ===')
    results = ocr.recognize(cropped)
    for r in results:
        print(f"  '{r.text}' (conf={r.confidence:.3f})")
    if not results:
        print('  [无结果]')

    if allowlist:
        print(f'\n=== OCR: allowlist={allowlist!r} ===')
        results = ocr.recognize(cropped, allowlist=allowlist)
        for r in results:
            print(f"  '{r.text}' (conf={r.confidence:.3f})")
        if not results:
            print('  [无结果]')

    print('\n=== OCR: 放大 4x 无白名单 ===')
    results = ocr.recognize(enlarged)
    for r in results:
        print(f"  '{r.text}' (conf={r.confidence:.3f})")
    if not results:
        print('  [无结果]')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='通用游戏截图 + OCR 调试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-c', '--config', default='usersettings.yaml', help='配置文件路径')
    parser.add_argument('-i', '--image', help='从本地图片加载 (跳过连接)')
    parser.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT_DIR), help='输出目录')
    parser.add_argument('--roi', help='OCR 区域 (x1,y1,x2,y2 相对坐标)')
    parser.add_argument('--allowlist', default='', help='OCR 字符白名单')
    parser.add_argument('--check-page', default=None, help='检查页面签名 (如 decisive_battle)')
    parser.add_argument('--pixel', action='append', help='查询像素点 (rx,ry)')
    args = parser.parse_args()

    out_dir = Path(args.output)

    if args.image:
        bgr = cv2.imread(args.image)
        if bgr is None:
            print(f'错误: 无法加载图片: {args.image}')
            sys.exit(1)
        screen = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        print(f'从图片加载: {args.image}')
    else:
        screen = capture_screenshot(args.config)

    print(f'截图尺寸: {screen.shape[1]}x{screen.shape[0]}')
    _save(screen, 'screenshot.png', out_dir)

    # 像素查询
    if args.pixel:
        print('\n=== 像素查询 ===')
        for p in args.pixel:
            rx, ry = map(float, p.split(','))
            _print_pixel_info(screen, rx, ry)

    # 页面签名检测
    if args.check_page is not None:
        check_page_signatures(screen, args.check_page or None)

    # ROI OCR
    if args.roi:
        parts = [float(x) for x in args.roi.split(',')]
        if len(parts) != 4:
            print('错误: --roi 需要 4 个逗号分隔的浮点数')
            sys.exit(1)
        run_ocr_on_roi(screen, tuple(parts), allowlist=args.allowlist, out_dir=out_dir)

    if not args.roi and args.check_page is None and not args.pixel:
        print('\n提示: 使用 --roi / --check-page / --pixel 执行进一步分析')
        print(f'截图已保存到: {out_dir.resolve()}')
        check_page_signatures(screen)


if __name__ == '__main__':
    main()
