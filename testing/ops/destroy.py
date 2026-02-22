"""舰船解装 (destroy_ships) 端到端测试。

用法::

    # 1. 全量解装（不过滤舰种）
    python testing/ops/destroy.py [serial]

    # 2. 只解装驱逐 + 轻巡
    python testing/ops/destroy.py [serial] --types DD CL

    # 3. 不卸装备直接解装
    python testing/ops/destroy.py [serial] --no-remove-equip

无页面前置要求 — destroy_ships() 内部通过 goto_page() 自动导航，
执行完毕后自动返回主页面。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from loguru import logger

from autowsgr.emulator import ADBController
from autowsgr.infra import setup_logger
from autowsgr.types import ShipType


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="舰船解装 E2E 测试")
    parser.add_argument(
        "serial",
        nargs="?",
        default=None,
        help="ADB 设备序列号，如 127.0.0.1:16384",
    )
    parser.add_argument(
        "--types",
        nargs="+",
        default=None,
        metavar="SHIP_TYPE",
        help=(
            "要解装的舰种简称列表，不传则解装全部。"
            f" 可选值: {', '.join(t.name for t in ShipType)}"
        ),
    )
    parser.add_argument(
        "--no-remove-equip",
        dest="remove_equipment",
        action="store_false",
        default=True,
        help="解装时不卸下装备",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    ship_types: list[ShipType] | None = None
    if args.types:
        try:
            ship_types = [ShipType[t] for t in args.types]
        except KeyError as exc:
            print(f"  [ERROR] 未知舰种: {exc}")
            print(f"  可用舰种: {', '.join(t.name for t in ShipType)}")
            sys.exit(1)

    setup_logger(log_dir=Path("logs/e2e/destroy"), level="DEBUG", save_images=True)

    print("=" * 60)
    print("  舰船解装 (destroy_ships) E2E 测试")
    print("=" * 60)
    print()
    print(f"  舰种列表  : {[t.name for t in ship_types] if ship_types else '全部'}")
    print(f"  卸下装备  : {args.remove_equipment}")
    print()

    steps = [
        "1. 连接设备",
        f"2. 调用 destroy_ships(ship_types={[t.name for t in ship_types] if ship_types else None}, remove_equipment={args.remove_equipment})",
        "3. 验证执行完成",
    ]
    print("  测试步骤:")
    for s in steps:
        print(f"    {s}")
    print()
    input("  按 Enter 开始运行...")
    print()

    ctrl = ADBController(serial=args.serial)
    try:
        dev = ctrl.connect()
        logger.info(f"已连接: {dev.serial}")
        print(f"  [OK] 已连接: {dev.serial}")

        from autowsgr.ops.destroy import destroy_ships

        destroy_ships(
            ctrl,
            ship_types=ship_types,
            remove_equipment=args.remove_equipment,
        )
        logger.info("destroy_ships() 已执行")
        print("  [OK] destroy_ships() 已执行")
    except Exception as exc:
        logger.opt(exception=True).error(f"测试失败: {exc}")
        print(f"  [FAIL] {exc}")
        ctrl.disconnect()
        sys.exit(1)

    ctrl.disconnect()
    print()

    result_desc = f"只解装 {[t.name for t in ship_types]}" if ship_types else "全量解装"
    print(f"  [OK] 舰船解装测试通过 — {result_desc}")



if __name__ == "__main__":
    main()
