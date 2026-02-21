"""浴室修理 (repair_in_bath) 端到端测试。

用法::

    python testing/ops/repair.py
    python testing/ops/repair.py 127.0.0.1:16384

无页面前置要求 — repair_in_bath() 内部通过 goto_page() 自动导航到浴室。
"""

from __future__ import annotations

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

_STEPS = [
    "1. 连接设备",
    "2. 调用 repair_in_bath(ctrl)",
    "3. 验证执行完成",
]


def main() -> None:
    serial = sys.argv[1] if len(sys.argv) > 1 else None
    setup_logger(log_dir=Path("logs/e2e/repair"), level="DEBUG", save_images=True)

    print("=" * 60)
    print("  浴室修理 (repair_in_bath) E2E 测试")
    print("=" * 60)
    print()
    print("  测试步骤:")
    for s in _STEPS:
        print(f"    {s}")
    print()
    input("  按 Enter 开始运行...")
    print()

    ctrl = ADBController(serial=serial)
    try:
        dev = ctrl.connect()
        logger.info(f"已连接: {dev.serial}")
        print(f"  [OK] 已连接: {dev.serial}")

        from autowsgr.ops.repair import repair_in_bath

        repair_in_bath(ctrl)
        logger.info("repair_in_bath() 已执行")
        print("  [OK] repair_in_bath() 已执行")
    except Exception as exc:
        logger.opt(exception=True).error(f"测试失败: {exc}")
        print(f"  [FAIL] {exc}")
        ctrl.disconnect()
        sys.exit(1)

    ctrl.disconnect()
    print()
    print("  [OK] 浴室修理测试通过")


if __name__ == "__main__":
    main()
