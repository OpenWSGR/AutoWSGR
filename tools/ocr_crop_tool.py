"""编队页与船池页 OCR 区域采集工具。

算法流程：
1. 通过随工具附带的 ADB 连接指定模拟器。
2. 使用 ``exec-out screencap -p`` 获取无损 PNG 截图。
3. 编队页按生产环境的六个槽位坐标裁切舰名、等级和舰种。
4. 编队空槽沿用生产环境的血条颜色探测规则过滤。
5. 船池页先缩放到 1280x720，再调用原生 DLL 定位名称横带。
6. 每条名称横带按固定七列映射到具体船卡。
7. 通过名称横带中的亮色文字过滤船池空卡。
8. 船池等级和舰种使用生产环境相同的相对偏移坐标。
9. 每个有效区域输出 1X、2X、3X、4X 四种图片。
10. 放大统一使用 INTER_CUBIC，保持 OCR 测试输入一致。
11. 时间戳模式按秒创建一次性目录。
12. 汇总模式按日期复用目录，并为每次采集追加序号。
13. 原始 ADB 截图保存在时间戳主目录。
14. team、pool 下始终创建 name、level、type 三类目录。
15. 所有输出均为 PNG，不依赖本机 Python 或 OCR 模型。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np


if TYPE_CHECKING:
    from argparse import Namespace


REFERENCE_WIDTH = 1280
REFERENCE_HEIGHT = 720
POOL_LIST_WIDTH = 1048
DEFAULT_SERIAL = '127.0.0.1:16384'
SCALES = (1, 2, 3, 4)

# 编队页坐标与 autowsgr/ui/battle/constants.py 保持一致。
TEAM_SLOT_CENTERS = (0.1146, 0.2292, 0.3438, 0.4583, 0.5729, 0.6875)
TEAM_NAME_Y_RANGE = (435 / REFERENCE_HEIGHT, 462 / REFERENCE_HEIGHT)
TEAM_NAME_HALF_WIDTH = (TEAM_SLOT_CENTERS[1] - TEAM_SLOT_CENTERS[0]) / 2
TEAM_BLOOD_PROBES = {
    slot: (center, 0.691) for slot, center in enumerate(TEAM_SLOT_CENTERS, start=1)
}
TEAM_LEVEL_CROPS = {
    1: (0.0496, 0.6104, 0.0941, 0.6319),
    2: (0.1640, 0.6104, 0.2085, 0.6319),
    3: (0.2785, 0.6104, 0.3230, 0.6319),
    4: (0.3930, 0.6104, 0.4375, 0.6319),
    5: (0.5074, 0.6104, 0.5519, 0.6319),
    6: (0.6219, 0.6104, 0.6664, 0.6319),
}
TEAM_TYPE_CROPS = {
    1: (0.0594, 0.6458, 0.0953, 0.6861),
    2: (0.1738, 0.6458, 0.2098, 0.6861),
    3: (0.2883, 0.6458, 0.3242, 0.6861),
    4: (0.4027, 0.6458, 0.4387, 0.6861),
    5: (0.5172, 0.6458, 0.5531, 0.6861),
    6: (0.6316, 0.6458, 0.6676, 0.6861),
}

# RGB 血条颜色。离哪个颜色最近，就使用哪个状态。
TEAM_BLOOD_COLORS = {
    'normal': (75, 168, 118),
    'moderate': (246, 184, 51),
    'severe': (171, 18, 17),
    'severe_prepare': (230, 58, 89),
    'empty_blood': (58, 60, 62),
    'no_ship': (43, 87, 112),
}

# 船池卡片中心来自 1280x720 船池页面。DLL 仅负责定位名称横带的纵坐标。
POOL_CARD_CENTERS_X = (122, 262, 402, 542, 682, 822, 962)
POOL_NAME_HALF_WIDTH = 70
POOL_NAME_TEXT_HALF_WIDTH = 58
POOL_NAME_BRIGHT_THRESHOLD = 180
POOL_NAME_BRIGHT_RATIO = 0.015
POOL_LEVEL_OFFSETS = (-62, -38, -2, -20)
POOL_TYPE_OFFSETS = (-62, -59, -13, -34.5)

PoolRowLocator = Callable[[np.ndarray], Sequence[Sequence[int]]]


class CropToolError(RuntimeError):
    """可直接展示给用户的工具错误。"""


@dataclass(frozen=True, slots=True)
class CropBox:
    """以原图像素表示的裁切框，允许半像素边界。"""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class CaptureTarget:
    """本次采集的输出目录与文件名序号。"""

    root: Path
    suffix: str


def _runtime_root() -> Path:
    """返回源码目录或打包后 ``main.exe`` 所在目录。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    """返回 PyInstaller 数据目录；源码运行时退回项目根目录。"""
    bundled = getattr(sys, '_MEIPASS', None)
    return Path(bundled).resolve() if bundled else _runtime_root()


def _config_path() -> Path:
    return _runtime_root() / 'config.json'


def _default_output_root() -> Path:
    return _runtime_root() / 'output'


def _read_saved_serial() -> str:
    """读取上次连接成功的设备地址，失败时使用默认模拟器。"""
    path = _config_path()
    if not path.is_file():
        return DEFAULT_SERIAL
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SERIAL
    serial = data.get('serial')
    return serial.strip() if isinstance(serial, str) and serial.strip() else DEFAULT_SERIAL


def _save_serial(serial: str) -> None:
    """记录最后成功连接的设备，供后续截图命令复用。"""
    path = _config_path()
    path.write_text(
        json.dumps({'serial': serial}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _resolve_adb_path(explicit: str | None = None) -> Path:
    """优先使用打包内置 ADB，其次使用项目环境或系统 ADB。"""
    candidates = [
        Path(explicit).expanduser() if explicit else None,
        _bundle_root() / 'adb' / 'adb.exe',
        _runtime_root() / 'adb' / 'adb.exe',
        Path(r'C:\ShiinaKuroko\01.Project\AutoWSGR-GUI\adb\adb.exe'),
        Path(sys.executable).resolve().parent
        / 'Lib'
        / 'site-packages'
        / 'adbutils'
        / 'binaries'
        / 'adb.exe',
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()

    system_adb = shutil.which('adb')
    if system_adb:
        return Path(system_adb).resolve()
    raise CropToolError('未找到 adb.exe，请使用打包后的完整工具目录')


def _run_adb(
    adb_path: Path,
    arguments: Sequence[str],
    *,
    binary: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """执行一次 ADB 命令，不弹出额外控制台窗口。"""
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    return subprocess.run(  # noqa: S603 - ADB 路径由工具目录或受信任配置解析。
        [str(adb_path), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
        encoding=None if binary else 'utf-8',
        errors=None if binary else 'replace',
        creationflags=creation_flags,
    )


def connect_device(adb_path: Path, serial: str) -> None:
    """连接设备并确认设备状态为 ``device``。"""
    result = _run_adb(adb_path, ['connect', serial])
    message = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        raise CropToolError(f'ADB 连接失败：{message or "未知错误"}')

    state = _run_adb(adb_path, ['-s', serial, 'get-state'])
    if state.returncode != 0 or state.stdout.strip() != 'device':
        detail = (state.stdout or state.stderr).strip()
        raise CropToolError(f'设备未就绪：{detail or serial}')
    _save_serial(serial)
    print(f'ADB 已连接：{serial}（{message}）')


def capture_adb_screen(adb_path: Path, serial: str) -> np.ndarray:
    """通过 ADB 获取无损 PNG，并解码为 OpenCV BGR 图像。"""
    connect_device(adb_path, serial)
    result = _run_adb(adb_path, ['-s', serial, 'exec-out', 'screencap', '-p'], binary=True)
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.decode(errors='replace').strip() if result.stderr else ''
        raise CropToolError(f'ADB 截图失败：{detail or "没有返回图片"}')

    encoded = np.frombuffer(result.stdout, dtype=np.uint8)
    screen = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if screen is None:
        raise CropToolError('ADB 截图不是有效的 PNG 图片')
    return screen


def _relative_box(
    screen: np.ndarray,
    region: tuple[float, float, float, float],
) -> CropBox:
    """把相对坐标转换为原图像素坐标。"""
    height, width = screen.shape[:2]
    left, top, right, bottom = region
    return CropBox(left * width, top * height, right * width, bottom * height)


def _offset_box(
    screen: np.ndarray,
    center_x: float,
    center_y: float,
    offsets: tuple[float, float, float, float],
) -> CropBox:
    """按 1280x720 基准偏移生成船池单卡裁切框。"""
    height, width = screen.shape[:2]
    left, top, right, bottom = offsets
    return CropBox(
        center_x + left * width / REFERENCE_WIDTH,
        center_y + top * height / REFERENCE_HEIGHT,
        center_x + right * width / REFERENCE_WIDTH,
        center_y + bottom * height / REFERENCE_HEIGHT,
    )


def _crop_scaled(screen: np.ndarray, box: CropBox, scale: int) -> np.ndarray:
    """按生产 OCR 的先取整、放大、再裁内边界流程生成图片。"""
    height, width = screen.shape[:2]
    left = max(0.0, min(float(width), box.left))
    right = max(0.0, min(float(width), box.right))
    top = max(0.0, min(float(height), box.top))
    bottom = max(0.0, min(float(height), box.bottom))
    if right <= left or bottom <= top:
        raise CropToolError('裁切坐标超出截图范围')

    source_left = math.floor(left)
    source_right = math.ceil(right)
    source_top = math.floor(top)
    source_bottom = math.ceil(bottom)
    source = screen[source_top:source_bottom, source_left:source_right]
    if source.size == 0:
        raise CropToolError('裁切结果为空')

    enlarged = source
    if scale != 1:
        enlarged = cv2.resize(
            source,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
    inner_left = round((left - source_left) * scale)
    inner_right = round((right - source_left) * scale)
    inner_top = round((top - source_top) * scale)
    inner_bottom = round((bottom - source_top) * scale)
    return enlarged[inner_top:inner_bottom, inner_left:inner_right].copy()


def _write_png(path: Path, image: np.ndarray) -> None:
    """使用 ``tofile`` 保存，兼容 Windows 中文路径。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode('.png', image)
    if not success:
        raise CropToolError(f'图片编码失败：{path.name}')
    encoded.tofile(str(path))


def _save_region_variants(
    screen: np.ndarray,
    box: CropBox,
    directory: Path,
    stem: str,
    suffix: str,
) -> int:
    """保存一个区域的 1X 至 4X 图片。"""
    for scale in SCALES:
        filename = f'{stem}-{scale}X{suffix}.png'
        _write_png(directory / filename, _crop_scaled(screen, box, scale))
    return len(SCALES)


def _nearest_blood_state(pixel_bgr: np.ndarray) -> str:
    """按 RGB 欧氏距离判断编队槽位是否为蓝色空位。"""
    pixel_rgb = np.asarray(pixel_bgr[::-1], dtype=np.float32)
    return min(
        TEAM_BLOOD_COLORS,
        key=lambda state: float(
            np.linalg.norm(pixel_rgb - np.asarray(TEAM_BLOOD_COLORS[state], dtype=np.float32))
        ),
    )


def _team_slot_occupied(screen: np.ndarray, slot: int) -> bool:
    """复用准备页血条探测点过滤空编队槽位。"""
    height, width = screen.shape[:2]
    x_ratio, y_ratio = TEAM_BLOOD_PROBES[slot]
    x = max(0, min(width - 1, round(x_ratio * width)))
    y = max(0, min(height - 1, round(y_ratio * height)))
    return _nearest_blood_state(screen[y, x]) != 'no_ship'


def _team_name_box(screen: np.ndarray, slot: int) -> CropBox:
    """返回单个编队槽位的舰名横带。"""
    center = TEAM_SLOT_CENTERS[slot - 1]
    top, bottom = TEAM_NAME_Y_RANGE
    return _relative_box(
        screen,
        (
            center - TEAM_NAME_HALF_WIDTH,
            top,
            center + TEAM_NAME_HALF_WIDTH,
            bottom,
        ),
    )


def crop_team(
    screen: np.ndarray,
    output_root: Path,
    suffix: str = '',
) -> tuple[int, int]:
    """裁切编队页，返回有效槽位数和保存图片数。"""
    valid_slots = 0
    saved_images = 0
    for slot in range(1, 7):
        if not _team_slot_occupied(screen, slot):
            continue

        valid_slots += 1
        boxes = {
            'name': _team_name_box(screen, slot),
            'level': _relative_box(screen, TEAM_LEVEL_CROPS[slot]),
            'type': _relative_box(screen, TEAM_TYPE_CROPS[slot]),
        }
        for kind, box in boxes.items():
            saved_images += _save_region_variants(
                screen,
                box,
                output_root / 'team' / kind,
                f'Team-slot-{slot}-{kind}',
                suffix,
            )
    return valid_slots, saved_images


def _load_pool_locator() -> PoolRowLocator:
    """延迟导入原生 DLL，便于显示清晰的缺失依赖错误。"""
    try:
        from autowsgr_native.recognition import locate
    except ImportError as exc:
        raise CropToolError('缺少船池定位 DLL，请使用打包后的完整工具目录') from exc
    return locate


def _locate_pool_rows(
    screen: np.ndarray,
    locator: PoolRowLocator | None = None,
) -> list[tuple[int, int]]:
    """把截图转换为 DLL 所需的 1280x720 格式并定位名称横带。"""
    legacy = cv2.resize(screen, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
    list_area = np.ascontiguousarray(legacy[:, :POOL_LIST_WIDTH])
    raw_rows = (locator or _load_pool_locator())(list_area)
    rows: list[tuple[int, int]] = []
    for raw_row in raw_rows:
        if len(raw_row) < 2:
            continue
        top, bottom = int(raw_row[0]), int(raw_row[1])
        if 0 <= top < bottom <= REFERENCE_HEIGHT:
            rows.append((top, bottom))
    return rows


def _pool_card_occupied(
    legacy_screen: np.ndarray,
    center_x: int,
    row: tuple[int, int],
) -> bool:
    """通过名称横带中的白色文字比例过滤船池空卡。"""
    top, bottom = row
    left = max(0, center_x - POOL_NAME_TEXT_HALF_WIDTH)
    right = min(POOL_LIST_WIDTH, center_x + POOL_NAME_TEXT_HALF_WIDTH)
    crop = legacy_screen[top:bottom, left:right]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray > POOL_NAME_BRIGHT_THRESHOLD)) >= POOL_NAME_BRIGHT_RATIO


def _pool_name_box(
    screen: np.ndarray,
    center_x_ref: int,
    row: tuple[int, int],
) -> CropBox:
    """把 DLL 名称横带裁成一张船卡对应的名称区域。"""
    height, width = screen.shape[:2]
    top, bottom = row
    return CropBox(
        (center_x_ref - POOL_NAME_HALF_WIDTH) * width / REFERENCE_WIDTH,
        top * height / REFERENCE_HEIGHT,
        (center_x_ref + POOL_NAME_HALF_WIDTH) * width / REFERENCE_WIDTH,
        bottom * height / REFERENCE_HEIGHT,
    )


def crop_pool(
    screen: np.ndarray,
    output_root: Path,
    suffix: str = '',
    *,
    locator: PoolRowLocator | None = None,
) -> tuple[int, int]:
    """裁切船池页，返回有效卡片数和保存图片数。"""
    rows = _locate_pool_rows(screen, locator)
    if not rows:
        raise CropToolError('DLL 未定位到船池名称条，请确认当前处于船池页面')

    legacy = cv2.resize(screen, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
    height, width = screen.shape[:2]
    valid_cards = 0
    saved_images = 0
    for row_index, row in enumerate(rows):
        row_center_ref = (row[0] + row[1]) / 2
        center_y = round(row_center_ref * height / REFERENCE_HEIGHT)
        for column_index, center_x_ref in enumerate(POOL_CARD_CENTERS_X):
            if not _pool_card_occupied(legacy, center_x_ref, row):
                continue

            slot = row_index * len(POOL_CARD_CENTERS_X) + column_index + 1
            center_x = round(center_x_ref * width / REFERENCE_WIDTH)
            valid_cards += 1
            boxes = {
                'name': _pool_name_box(screen, center_x_ref, row),
                'level': _offset_box(screen, center_x, center_y, POOL_LEVEL_OFFSETS),
                'type': _offset_box(screen, center_x, center_y, POOL_TYPE_OFFSETS),
            }
            for kind, box in boxes.items():
                saved_images += _save_region_variants(
                    screen,
                    box,
                    output_root / 'pool' / kind,
                    f'Pool-slot-{slot}-{kind}',
                    suffix,
                )
    if valid_cards == 0:
        raise CropToolError('DLL 找到名称条，但没有检测到有效船卡')
    return valid_cards, saved_images


def _ensure_output_tree(root: Path) -> None:
    """创建固定的 team/pool/name/level/type 目录结构。"""
    for page in ('team', 'pool'):
        for kind in ('name', 'level', 'type'):
            (root / page / kind).mkdir(parents=True, exist_ok=True)


def _next_capture_sequence(root: Path, page: str) -> int:
    """根据原始截图数量生成不会覆盖旧数据的采集序号。"""
    return len(list(root.glob(f'adb-{page}*.png'))) + 1


def prepare_capture_target(
    output_root: Path,
    mode: str,
    page: str,
    now: datetime | None = None,
) -> CaptureTarget:
    """创建时间戳目录，并计算汇总模式的文件名后缀。"""
    current = now or datetime.now().astimezone()
    if mode == 'timestamp':
        root = output_root / current.strftime('%Y%m%d-%H%M%S')
        root.mkdir(parents=True, exist_ok=True)
        _ensure_output_tree(root)
        sequence = _next_capture_sequence(root, page)
        suffix = '' if sequence == 1 else f'-{sequence:03d}'
        return CaptureTarget(root=root, suffix=suffix)

    root = output_root / current.strftime('%Y%m%d')
    root.mkdir(parents=True, exist_ok=True)
    _ensure_output_tree(root)
    sequence = _next_capture_sequence(root, page)
    return CaptureTarget(root=root, suffix=f'-{sequence:03d}')


def _save_source_screen(
    screen: np.ndarray,
    target: CaptureTarget,
    page: str,
) -> Path:
    """把原始 ADB 截图保存到时间戳主目录。"""
    path = target.root / f'adb-{page}{target.suffix}.png'
    _write_png(path, screen)
    return path


def _normalize_mode(value: str) -> str:
    """允许用户使用 A/B 简写两种归档模式。"""
    normalized = value.lower()
    aliases = {
        'a': 'timestamp',
        'timestamp': 'timestamp',
        'b': 'summary',
        'summary': 'summary',
    }
    if normalized not in aliases:
        raise argparse.ArgumentTypeError('模式只能是 A/timestamp 或 B/summary')
    return aliases[normalized]


def _add_capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--mode',
        '-m',
        type=_normalize_mode,
        default='timestamp',
        help='A/timestamp：按秒建目录；B/summary：按日期汇总（默认 A）',
    )
    parser.add_argument('--serial', help='设备地址；默认使用最后连接的设备')
    parser.add_argument('--output', type=Path, help='输出根目录；默认是工具旁的 output')
    parser.add_argument('--adb-path', help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    """创建 ``main.exe`` 命令行解析器。"""
    parser = argparse.ArgumentParser(
        prog='main',
        description='AutoWSGR 编队页/船池页 OCR 裁切工具',
    )
    subparsers = parser.add_subparsers(dest='command')

    adb_parser = subparsers.add_parser('adb', help='连接模拟器')
    adb_parser.add_argument('serial', nargs='?', help=f'设备地址，默认 {DEFAULT_SERIAL}')
    adb_parser.add_argument('--adb-path', help=argparse.SUPPRESS)

    team_parser = subparsers.add_parser('team', help='采集编队页')
    _add_capture_arguments(team_parser)

    pool_parser = subparsers.add_parser('pool', help='采集船池页')
    _add_capture_arguments(pool_parser)
    return parser


def _run_capture(args: Namespace) -> int:
    """执行 team 或 pool 采集命令。"""
    adb_path = _resolve_adb_path(args.adb_path)
    serial = args.serial or _read_saved_serial()
    screen = capture_adb_screen(adb_path, serial)
    output_root = (args.output or _default_output_root()).expanduser().resolve()
    target = prepare_capture_target(output_root, args.mode, args.command)
    source_path = _save_source_screen(screen, target, args.command)

    if args.command == 'team':
        valid_items, saved_images = crop_team(screen, target.root, target.suffix)
        item_name = '有效编队槽位'
    else:
        valid_items, saved_images = crop_pool(screen, target.root, target.suffix)
        item_name = '有效船池卡片'

    print(f'原始截图：{source_path}')
    print(f'{item_name}：{valid_items}')
    print(f'裁切图片：{saved_images}')
    print(f'输出目录：{target.root}')
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == 'adb':
            adb_path = _resolve_adb_path(args.adb_path)
            connect_device(adb_path, args.serial or _read_saved_serial())
            return 0
        return _run_capture(args)
    except CropToolError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
