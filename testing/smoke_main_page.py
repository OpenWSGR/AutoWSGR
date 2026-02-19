"""主页面自动化冒烟测试 — 利用退出控件自动回退状态。

运行方式::

    # 使用默认 serial
    python testing/smoke_main_page.py

    # 指定 serial
    python testing/smoke_main_page.py emulator-5554

    # DEBUG 模式
    python testing/smoke_main_page.py emulator-5554 --debug

前置条件：
    1. 模拟器已启动
    2. 游戏已打开并位于 **主页面** (母港/秘书舰界面)

测试流程：
    对 4 个导航控件 (出征 / 任务 / 侧边栏 / 主页) 依次:
    1. 验证当前在主页面
    2. 点击导航控件进入子页面
    3. 验证已离开主页面
    4. 点击退出控件返回主页面
    5. 验证已返回主页面

    每个步骤自动通过退出控件回退，无需人工操作。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── 把项目根目录加入 path ──
sys.path.insert(0, str(Path(__file__).parent.parent))

from autowsgr.emulator.controller import ADBController
from autowsgr.infra.logger import save_image, setup_logger
from autowsgr.ui.main_page import MainPage, MainPageTarget

# ── 配置 ──

LOG_DIR = Path("logs/smoke")
PAUSE_AFTER_ACTION = 1.5  # 导航/退出后等待 UI 动画完成
TARGETS = [
    MainPageTarget.SORTIE,
    MainPageTarget.TASK,
    MainPageTarget.SIDEBAR,
    MainPageTarget.HOME,
]


# ── 工具函数 ──


def step(title: str) -> bool:
    """打印步骤标题，询问是否执行。"""
    print()
    print("─" * 60)
    print(f"  步骤: {title}")
    print("─" * 60)
    ans = input("  [Enter] 执行  |  [s] 跳过  |  [q] 退出: ").strip().lower()
    if ans == "q":
        print("  用户中止测试。")
        sys.exit(0)
    return ans != "s"


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ {msg}")


def verify_main_page(ctrl: ADBController, tag: str = "") -> bool:
    """截图并验证是否在主页面。"""
    screen = ctrl.screenshot()
    if tag:
        save_image(screen, tag=f"main_{tag}")
    is_main = MainPage.is_current_page(screen)
    if is_main:
        ok("当前在主页面")
    else:
        fail("当前不在主页面!")
    return is_main


def test_roundtrip(
    ctrl: ADBController,
    page: MainPage,
    target: MainPageTarget,
) -> bool:
    """执行一次导航 → 验证 → 退出 → 验证的完整回路。

    Returns
    -------
    bool
        回路是否全部成功。
    """
    label = target.value
    success = True

    # 1. 验证在主页面
    info(f"[{label}] 导航前验证...")
    screen = ctrl.screenshot()
    if not MainPage.is_current_page(screen):
        fail(f"[{label}] 导航前不在主页面，跳过此目标")
        return False
    ok(f"[{label}] 导航前: 在主页面")

    # 2. 点击导航
    info(f"[{label}] 点击导航控件...")
    page.navigate_to(target)
    time.sleep(PAUSE_AFTER_ACTION)

    # 3. 验证离开主页面
    screen = ctrl.screenshot()
    save_image(screen, tag=f"main_nav_{label}")
    still_main = MainPage.is_current_page(screen)
    if still_main:
        fail(f"[{label}] 点击后仍在主页面 — 导航可能无效")
        success = False
    else:
        ok(f"[{label}] 已离开主页面")

    # 4. 点击退出
    info(f"[{label}] 点击退出控件...")
    page.return_from(target)
    time.sleep(PAUSE_AFTER_ACTION)

    # 5. 验证回到主页面
    screen = ctrl.screenshot()
    save_image(screen, tag=f"main_ret_{label}")
    back_main = MainPage.is_current_page(screen)
    if back_main:
        ok(f"[{label}] 已返回主页面 ✓")
    else:
        fail(f"[{label}] 退出后未回到主页面!")
        success = False

    return success


# ── 主流程 ──


def main() -> None:
    # ── 解析参数 ──
    serial = None
    debug = False
    for arg in sys.argv[1:]:
        if arg == "--debug":
            debug = True
        else:
            serial = arg

    setup_logger(
        log_dir=LOG_DIR,
        level="DEBUG" if debug else "INFO",
        save_images=True,
    )

    print()
    print("═" * 60)
    print("  主页面 自动化冒烟测试")
    print("═" * 60)
    print()
    print("  请确保游戏已打开并位于【主页面】(母港/秘书舰界面)")
    print("  每个导航目标自动点击退出控件回退，无需人工操作")
    print()

    # ── 连接设备 ──
    if not step("连接设备并验证主页面"):
        return

    ctrl = ADBController(serial=serial, screenshot_timeout=15.0)
    ctrl.connect()
    ok(f"已连接: {ctrl._serial}")

    if not verify_main_page(ctrl, tag="step0_connect"):
        fail("请先回到主页面再运行测试!")
        ctrl.disconnect()
        return

    page = MainPage(ctrl)

    # ── 逐一测试 4 个导航目标 ──
    results: dict[str, bool] = {}

    for target in TARGETS:
        label = target.value
        if step(f"测试导航: {label}"):
            results[label] = test_roundtrip(ctrl, page, target)
        else:
            results[label] = True  # 跳过视为通过
            info(f"已跳过 [{label}]")

    # ── 最终状态 ──
    if step("最终状态验证"):
        verify_main_page(ctrl, tag="step_final")

    # ── 汇总 ──
    ctrl.disconnect()
    print()
    print("═" * 60)
    print("  测试结果汇总")
    print("═" * 60)
    all_pass = True
    for label, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"    {label:8s}  {status}")
        if not passed:
            all_pass = False
    print()
    if all_pass:
        print("  全部通过!")
    else:
        print("  存在失败项，请检查截图日志。")
    print(f"  截图目录: {(LOG_DIR / 'images').resolve()}")
    print("═" * 60)


if __name__ == "__main__":
    main()
