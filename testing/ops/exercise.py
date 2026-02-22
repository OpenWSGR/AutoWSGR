"""演习 (run_exercise) 端到端测试。

用法::

    python testing/ops/exercise.py
    python testing/ops/exercise.py 127.0.0.1:16384

    # 指定舰队和对手 (对手编号 1–5，不传则挑战所有可用对手)
    python testing/ops/exercise.py 127.0.0.1:16384 --fleet 2 --rival 3

无页面前置要求 — ExerciseRunner 内部通过 goto_page() 自动导航到演习面板。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass

from loguru import logger

from autowsgr.emulator import ADBController
from autowsgr.infra import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="演习端到端测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "serial",
        nargs="?",
        default=None,
        metavar="SERIAL",
        help="ADB serial (留空则自动检测唯一设备)",
    )
    parser.add_argument(
        "--fleet",
        type=int,
        default=1,
        metavar="N",
        help="出战舰队编号 (默认: 1)",
    )
    parser.add_argument(
        "--rival",
        type=int,
        default=None,
        metavar="N",
        help="指定对手编号 1–5；不传则挑战所有可用对手",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    setup_logger(log_dir=Path("logs/e2e/exercise"), level="DEBUG", save_images=True)

    rivalry_desc = f"对手 {args.rival}" if args.rival is not None else "全部可用对手"

    _steps = [
        "1. 连接设备",
        f"2. 导航至演习面板 (舰队 {args.fleet})",
        f"3. 挑战{rivalry_desc}",
        "4. 打印每场战斗结果",
    ]

    print("=" * 60)
    print("  演习 (run_exercise) E2E 测试")
    print("=" * 60)
    print()
    print("  测试步骤:")
    for s in _steps:
        print(f"    {s}")
    print()
    if args.rival is not None and not (1 <= args.rival <= 5):
        print(f"  [ERROR] --rival 必须在 1–5 之间，收到: {args.rival}")
        sys.exit(1)
    input("  按 Enter 开始运行...")
    print()

    ctrl = ADBController(serial=args.serial)
    try:
        dev = ctrl.connect()
        logger.info("已连接: {}", dev.serial)
        print(f"  [OK] 已连接: {dev.serial}")

        from autowsgr.ops.exercise import run_exercise

        results = run_exercise(ctrl, fleet_id=args.fleet, rival=args.rival)
        logger.info("run_exercise() 返回 {} 场结果", len(results))
        print(f"  [OK] 完成 {len(results)} 场演习")
        print()
        for i, r in enumerate(results, start=1):
            flag = r.flag.name if hasattr(r.flag, "name") else str(r.flag)
            print(f"    第 {i} 场: flag={flag}  节点数={r.node_count}")

    except Exception as exc:
        logger.opt(exception=True).error("测试失败: {}", exc)
        print(f"  [FAIL] {exc}")
        ctrl.disconnect()
        sys.exit(1)

    ctrl.disconnect()
    print()
    print("  [OK] 演习测试通过")


if __name__ == "__main__":
    main()
