"""食堂做菜 (cook) 端到端测试。

用法::

    python testing/ops/cook.py
    python testing/ops/cook.py 127.0.0.1:16384

无页面前置要求 — cook() 内部通过 goto_page() 自动导航到食堂。
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
    "2. 调用 cook(ctrl, position=recipe, force_cook=False)",
    "3. 打印做菜结果",
]


def main() -> None:
    serial = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdecimal() else None
    recipe = int(sys.argv[2]) if len(sys.argv) > 2 else (int(sys.argv[1]) if sys.argv[1].isdecimal() else 1)
    setup_logger(log_dir=Path("logs/e2e/cook"), level="DEBUG", save_images=True)

    print("=" * 60)
    print("  食堂做菜 (cook) E2E 测试")
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

        from autowsgr.ops.cook import cook

        result = cook(ctrl, position=recipe, force_cook=False)
        logger.info(f"cook() 返回: {result}")
        print(f"  [OK] cook() = {result}")
    except Exception as exc:
        logger.opt(exception=True).error(f"测试失败: {exc}")
        print(f"  [FAIL] {exc}")
        ctrl.disconnect()
        sys.exit(1)

    ctrl.disconnect()
    print()
    print("  [OK] 食堂做菜测试通过")


if __name__ == "__main__":
    main()
