"""模拟器层冒烟测试 — 人类监督下的交互验证。

运行方式::

    # 使用默认 serial（自动检测）
    python testing/smoke_emulator.py

    # 指定 serial
    python testing/smoke_emulator.py emulator-5554
    python testing/smoke_emulator.py 127.0.0.1:16384

    # 指定 DEBUG 级别（可看到详细坐标日志）
    python testing/smoke_emulator.py --debug

前置条件：
    1. 模拟器已启动并处于运行状态
    2. ADB 可访问设备（adb devices 有输出）

测试流程：
    1. 连接设备 → 取分辨率
    2. 截图 → 保存到 logs/smoke/images/
    3. 点击屏幕中心（0.5, 0.5）
    4. 从左向右滑动
    5. 检查游戏应用是否在运行
    6. 可选：启动 / 停止游戏应用
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ── 把项目根目录加入 path ──
sys.path.insert(0, str(Path(__file__).parent.parent))

from autowsgr.emulator.controller import ADBController
from autowsgr.infra.logger import save_image, setup_logger
from autowsgr.types import GameAPP

# ── 配置 ──────────────────────────────────────────────────────────────────────

LOG_DIR = Path("logs/smoke")
GAME_PACKAGE = GameAPP.official.package_name       # 官服：com.huanmeng.zhanjian2

# ── 工具函数 ──────────────────────────────────────────────────────────────────


def step(title: str) -> bool:
    """打印步骤标题，询问是否执行。返回 True = 继续，False = 跳过。"""
    print()
    print("─" * 60)
    print(f"  步骤: {title}")
    print("─" * 60)
    ans = input("  [Enter] 执行  |  [s + Enter] 跳过  |  [q + Enter] 退出: ").strip().lower()
    if ans == "q":
        print("  用户中止测试。")
        sys.exit(0)
    return ans != "s"


def show_ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def show_fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def run_with_retry(fn: "Callable[[], None]", label: str, max_retries: int = 2) -> bool:
    """执行 fn，失败时允许用户最多重试 max_retries 次。返回最终是否成功。"""
    from loguru import logger

    for attempt in range(max_retries + 1):
        try:
            fn()
            return True
        except Exception as exc:
            show_fail(f"{exc}")
            logger.exception("{} 异常（第 {}/{} 次）", label, attempt + 1, max_retries + 1)
            if attempt < max_retries:
                ans = input(
                    f"  [r + Enter] 重试 ({attempt + 1}/{max_retries})  |  任意键跳过: "
                ).strip().lower()
                if ans == "r":
                    print(f"  ↺ 正在重试第 {attempt + 2} 次 …")
                    continue
            return False
    return False  # unreachable


# ── 主流程 ────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── 解析参数 ──
    serial: str | None = None
    debug_mode = False
    for arg in sys.argv[1:]:
        if arg == "--debug":
            debug_mode = True
        elif not arg.startswith("-"):
            serial = arg

    # ── 初始化日志（在 import airtest 之前调用，确保噪音静默生效）──
    log_level = "DEBUG" if debug_mode else "INFO"
    setup_logger(log_dir=LOG_DIR, level=log_level, save_images=True)
    from loguru import logger
    logger.info("serial={}, log_dir={}, level={}", serial or "auto", LOG_DIR, log_level)

    ctrl = ADBController(serial=serial, screenshot_timeout=15.0)

    print()
    print("=" * 60)
    print("  AutoWSGR V2 — 模拟器层冒烟测试")
    print("=" * 60)
    print(f"  目标设备  : {serial or '自动检测'}")
    print(f"  日志目录  : {LOG_DIR.resolve()}")
    print(f"  日志级别  : {log_level}")
    print()
    print("  请确认以下前置条件已满足：")
    print("    1. 模拟器已启动")
    print("    2. adb devices 可看到设备")
    input("  按 Enter 开始测试 ... ")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 1: 连接设备
    # ══════════════════════════════════════════════════════════════════════════
    if step("连接设备（connect）"):
        def _connect() -> None:
            info = ctrl.connect()
            show_ok(f"设备已连接: serial={info.serial}  分辨率={info.resolution[0]}x{info.resolution[1]}")

        ok = run_with_retry(_connect, "连接设备")
        if not ok:
            print("\n  连接失败，无法继续测试。请检查模拟器和 ADB 环境。")
            sys.exit(1)

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 2: 截图
    # ══════════════════════════════════════════════════════════════════════════
    if step("截图（screenshot）"):
        def _screenshot() -> None:
            t0 = time.monotonic()
            screen = ctrl.screenshot()
            elapsed = time.monotonic() - t0
            show_ok(f"截图成功: shape={screen.shape}  耗时={elapsed:.3f}s")

            path = save_image(screen, tag="smoke_init")
            if path:
                show_ok(f"截图已保存: {path}")

            # 打印右下角像素供参考
            h, w = screen.shape[:2]
            r, g, b = int(screen[h - 1, w - 1, 0]), int(screen[h - 1, w - 1, 1]), int(screen[h - 1, w - 1, 2])
            show_ok(f"右下角像素 RGB=({r},{g},{b})")

        run_with_retry(_screenshot, "截图")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 3: 点击屏幕中心
    # ══════════════════════════════════════════════════════════════════════════
    if step("点击屏幕中心 click(0.5, 0.5)  ⚠ 这会实际触发点击！"):
        def _click() -> None:
            ctrl.click(0.5, 0.5)
            show_ok("click(0.5, 0.5) 已发送")
            time.sleep(0.5)
            path = save_image(ctrl.screenshot(), tag="smoke_after_click")
            if path:
                show_ok(f"点击后截图: {path}")

        run_with_retry(_click, "点击")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 4-a: 向右滑动（左 → 右）
    # ══════════════════════════════════════════════════════════════════════════
    if step("向右滑动 swipe(0.3, 0.5 → 0.9, 0.5)  ⚠ 会实际触发滑动！"):
        def _swipe_right() -> None:
            ctrl.swipe(0.3, 0.5, 0.9, 0.5, duration=0.5)
            show_ok("swipe 左→右 已发送")
            time.sleep(0.5)

        run_with_retry(_swipe_right, "向右滑动")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 4-b: 向左滑动（右 → 左）
    # ══════════════════════════════════════════════════════════════════════════
    if step("向左滑动 swipe(0.9, 0.5 → 0.3, 0.5)  ⚠ 会实际触发滑动！"):
        def _swipe_left() -> None:
            ctrl.swipe(0.9, 0.5, 0.3, 0.5, duration=0.5)
            show_ok("swipe 右→左 已发送")
            time.sleep(0.5)

        run_with_retry(_swipe_left, "向左滑动")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 5: 长按屏幕中心
    # ══════════════════════════════════════════════════════════════════════════
    if step("长按屏幕中心 long_tap(0.5, 0.5, 1.5s)  ⚠ 会触发长按！"):
        def _long_tap() -> None:
            ctrl.long_tap(0.5, 0.5, duration=1.5)
            show_ok("long_tap(0.5, 0.5, 1.5s) 已发送")
            time.sleep(0.3)

        run_with_retry(_long_tap, "长按")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 6: 按下 HOME 键（KeyCode 3）
    # ══════════════════════════════════════════════════════════════════════════
    if step("按下 HOME 键 key_event(3)  ⚠ 会将游戏退到后台！"):
        def _home() -> None:
            ctrl.key_event(3)
            show_ok("key_event(3=HOME) 已发送")
            time.sleep(0.5)
            path = save_image(ctrl.screenshot(), tag="smoke_after_home")
            if path:
                show_ok(f"HOME 后截图: {path}")

        run_with_retry(_home, "HOME 键")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 7: 检查游戏应用状态
    # ══════════════════════════════════════════════════════════════════════════
    if step(f"检查游戏应用状态  package={GAME_PACKAGE}"):
        def _is_running() -> None:
            running = ctrl.is_app_running(GAME_PACKAGE)
            show_ok(f"is_app_running('{GAME_PACKAGE}') = {running}")

        run_with_retry(_is_running, "is_app_running")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 8: 启动游戏
    # ══════════════════════════════════════════════════════════════════════════
    if step(f"启动游戏 start_app('{GAME_PACKAGE}')  ⚠ 会实际启动应用！"):
        def _start_app() -> None:
            ctrl.start_app(GAME_PACKAGE)
            show_ok("start_app 已调用，等待 3s ...")
            time.sleep(3)
            path = save_image(ctrl.screenshot(), tag="smoke_after_start_app")
            if path:
                show_ok(f"启动后截图: {path}")

        run_with_retry(_start_app, "启动应用")

    # ══════════════════════════════════════════════════════════════════════════
    # 步骤 9: shell 命令
    # ══════════════════════════════════════════════════════════════════════════
    if step("执行 shell 命令  cmd='getprop ro.product.model'"):
        def _shell() -> None:
            output = ctrl.shell("getprop ro.product.model")
            show_ok(f"shell 输出: '{output.strip()}'")

        run_with_retry(_shell, "shell 命令")

    # ══════════════════════════════════════════════════════════════════════════
    # 断开连接
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("─" * 60)
    ctrl.disconnect()
    show_ok("设备已断开")

    print()
    print("=" * 60)
    print("  冒烟测试完成！")
    print(f"  截图存储在: {(LOG_DIR / 'images').resolve()}")
    print("=" * 60)
    logger.info("=== 模拟器层冒烟测试结束 ===")


if __name__ == "__main__":
    main()
