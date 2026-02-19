"""出征准备页面交互式测试 — 人类监督下验证 UI 控制器。

运行方式::

    # 使用默认 serial
    python testing/smoke_battle_preparation.py

    # 指定 serial
    python testing/smoke_battle_preparation.py emulator-5554

    # DEBUG 模式
    python testing/smoke_battle_preparation.py emulator-5554 --debug

前置条件：
    1. 模拟器已启动
    2. 游戏已打开并进入 **出征准备** 页面
       （从主页 → 出征 → 选择地图 → 出征准备）

测试流程：
    1. 连接设备 → 截图 → 验证当前是否为出征准备页面
    2. 读取当前状态（舰队、面板、自动补给）
    3. 依次测试各个操作（舰队切换、面板切换、开关）
    4. 每步操作后截图验证状态变化
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# ── 把项目根目录加入 path ──
sys.path.insert(0, str(Path(__file__).parent.parent))

from autowsgr.emulator.controller import ADBController
from autowsgr.infra.logger import save_image, setup_logger
from autowsgr.ui.battle_preparation import BattlePreparationPage, Panel

# ── 配置 ──

LOG_DIR = Path("logs/smoke")
PAUSE_AFTER_ACTION = 0.8  # 每个动作执行后等待秒数，让 UI 动画完成


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


def read_state(ctrl: ADBController, tag: str = "") -> None:
    """截图并报告页面状态。"""
    screen = ctrl.screenshot()
    if tag:
        save_image(screen, tag=f"bp_{tag}")

    is_page = BattlePreparationPage.is_current_page(screen)
    fleet = BattlePreparationPage.get_selected_fleet(screen)
    panel = BattlePreparationPage.get_active_panel(screen)
    auto = BattlePreparationPage.is_auto_supply_enabled(screen)

    if is_page:
        ok("当前是出征准备页面")
    else:
        fail("当前不是出征准备页面")

    info(f"选中舰队: {fleet}队" if fleet else "选中舰队: 无法识别")
    info(f"当前面板: {panel.value}" if panel else "当前面板: 无法识别")
    info(f"自动补给: {'✓ 启用' if auto else '✗ 关闭'}")

    return screen


def verify_fleet(ctrl: ADBController, expected: int) -> None:
    """截图验证舰队选中状态。"""
    time.sleep(PAUSE_AFTER_ACTION)
    screen = ctrl.screenshot()
    actual = BattlePreparationPage.get_selected_fleet(screen)
    if actual == expected:
        ok(f"舰队切换验证通过: {actual}队")
    else:
        fail(f"期望 {expected}队, 实际 {actual}队")


def verify_panel(ctrl: ADBController, expected: Panel) -> None:
    """截图验证面板选中状态。"""
    time.sleep(PAUSE_AFTER_ACTION)
    screen = ctrl.screenshot()
    actual = BattlePreparationPage.get_active_panel(screen)
    if actual == expected:
        ok(f"面板切换验证通过: {actual.value}")
    else:
        fail(f"期望 {expected.value}, 实际 {actual.value if actual else '无法识别'}")


# ── 主流程 ──


def main() -> None:
    # ── 解析参数 ──
    serial: str | None = None
    debug_mode = False
    for arg in sys.argv[1:]:
        if arg == "--debug":
            debug_mode = True
        elif not arg.startswith("-"):
            serial = arg

    log_level = "DEBUG" if debug_mode else "INFO"
    setup_logger(log_dir=LOG_DIR, level=log_level, save_images=True)
    from loguru import logger
    logger.info("=== 出征准备页面交互式测试开始 ===")

    print()
    print("=" * 60)
    print("  AutoWSGR V2 — 出征准备页面 交互式测试")
    print("=" * 60)
    print(f"  目标设备  : {serial or '自动检测'}")
    print(f"  日志目录  : {LOG_DIR.resolve()}")
    print()
    print("  ⚠ 请确保游戏已打开并进入「出征准备」页面")
    print("  ⚠ 测试过程中会实际操作游戏界面")
    input("  按 Enter 开始 ... ")

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 连接设备
    # ═══════════════════════════════════════════════════════════════════════
    ctrl = ADBController(serial=serial, screenshot_timeout=15.0)

    if step("连接设备"):
        try:
            dev_info = ctrl.connect()
            ok(f"已连接: {dev_info.serial}  分辨率: {dev_info.resolution[0]}x{dev_info.resolution[1]}")
        except Exception as exc:
            fail(f"连接失败: {exc}")
            sys.exit(1)

    page = BattlePreparationPage(ctrl)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 读取初始状态
    # ═══════════════════════════════════════════════════════════════════════
    if step("读取当前页面状态"):
        read_state(ctrl, tag="initial")

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 舰队切换: 1 → 2 → 3 → 4 → 1
    # ═══════════════════════════════════════════════════════════════════════
    if step("舰队切换: 依次选择 2队 → 3队 → 4队 → 1队"):
        for fleet in [2, 3, 4, 1]:
            info(f"切换到 {fleet}队 ...")
            page.select_fleet(fleet)
            verify_fleet(ctrl, fleet)
        save_image(ctrl.screenshot(), tag="bp_fleet_done")

    # ═══════════════════════════════════════════════════════════════════════
    # 4. 面板切换: 综合战力 → 快速补给 → 快速修理 → 装备预览 → 综合战力
    # ═══════════════════════════════════════════════════════════════════════
    if step("面板切换: 快速补给 → 快速修理 → 装备预览 → 综合战力"):
        for panel in [Panel.QUICK_SUPPLY, Panel.QUICK_REPAIR, Panel.EQUIPMENT, Panel.STATS]:
            info(f"切换到 [{panel.value}] ...")
            page.select_panel(panel)
            verify_panel(ctrl, panel)
        save_image(ctrl.screenshot(), tag="bp_panel_done")

    # ═══════════════════════════════════════════════════════════════════════
    # 5. 快速补给（便捷方法）
    # ═══════════════════════════════════════════════════════════════════════
    if step("快速补给 (quick_supply)"):
        page.quick_supply()
        verify_panel(ctrl, Panel.QUICK_SUPPLY)
        save_image(ctrl.screenshot(), tag="bp_quick_supply")

    # ═══════════════════════════════════════════════════════════════════════
    # 6. 快速修理（便捷方法）
    # ═══════════════════════════════════════════════════════════════════════
    if step("快速修理 (quick_repair)"):
        page.quick_repair()
        verify_panel(ctrl, Panel.QUICK_REPAIR)
        save_image(ctrl.screenshot(), tag="bp_quick_repair")

    # ═══════════════════════════════════════════════════════════════════════
    # 7. 自动补给开关
    # ═══════════════════════════════════════════════════════════════════════
    if step("切换自动补给开关 (toggle_auto_supply)\n           ⚠ 会点击两次，先关再开（恢复原状态）"):
        # 先读初始状态
        screen = ctrl.screenshot()
        was_on = BattlePreparationPage.is_auto_supply_enabled(screen)
        info(f"当前自动补给: {'启用' if was_on else '关闭'}")

        # 第一次切换
        info("第一次切换 ...")
        page.toggle_auto_supply()
        time.sleep(PAUSE_AFTER_ACTION)
        screen = ctrl.screenshot()
        now = BattlePreparationPage.is_auto_supply_enabled(screen)
        if now != was_on:
            ok(f"切换成功: {'启用' if was_on else '关闭'} → {'启用' if now else '关闭'}")
        else:
            fail(f"切换无效: 状态未改变 ({'启用' if now else '关闭'})")
        save_image(screen, tag="bp_auto_supply_toggled")

        # 第二次切换，恢复原状态
        info("第二次切换（恢复原状态）...")
        page.toggle_auto_supply()
        time.sleep(PAUSE_AFTER_ACTION)
        screen = ctrl.screenshot()
        restored = BattlePreparationPage.is_auto_supply_enabled(screen)
        if restored == was_on:
            ok(f"已恢复: {'启用' if restored else '关闭'}")
        else:
            fail(f"恢复失败: 期望 {'启用' if was_on else '关闭'}, 实际 {'启用' if restored else '关闭'}")

    # ═══════════════════════════════════════════════════════════════════════
    # 8. 战役支援开关
    # ═══════════════════════════════════════════════════════════════════════
    if step("切换战役支援 (toggle_battle_support)\n           ⚠ 会点击两次（恢复原状态）"):
        info("第一次切换 ...")
        page.toggle_battle_support()
        time.sleep(PAUSE_AFTER_ACTION)
        save_image(ctrl.screenshot(), tag="bp_support_toggled")
        ok("已点击战役支援开关")

        info("第二次切换（恢复原状态）...")
        page.toggle_battle_support()
        time.sleep(PAUSE_AFTER_ACTION)
        save_image(ctrl.screenshot(), tag="bp_support_restored")
        ok("已恢复战役支援开关")

    # ═══════════════════════════════════════════════════════════════════════
    # 9. 综合状态验证
    # ═══════════════════════════════════════════════════════════════════════
    if step("最终状态读取"):
        read_state(ctrl, tag="final")

    # ═══════════════════════════════════════════════════════════════════════
    # 10. 回退（可选）
    # ═══════════════════════════════════════════════════════════════════════
    if step("回退 (go_back)  ⚠ 会离开出征准备页面！"):
        page.go_back()
        time.sleep(PAUSE_AFTER_ACTION)
        screen = ctrl.screenshot()
        save_image(screen, tag="bp_after_back")
        is_still = BattlePreparationPage.is_current_page(screen)
        if is_still:
            fail("回退后仍被识别为出征准备页面")
        else:
            ok("已离开出征准备页面")

    # ═══════════════════════════════════════════════════════════════════════
    # 结束
    # ═══════════════════════════════════════════════════════════════════════
    print()
    print("─" * 60)
    ctrl.disconnect()
    ok("设备已断开")

    print()
    print("=" * 60)
    print("  出征准备页面交互式测试完成！")
    print(f"  截图存储在: {(LOG_DIR / 'images').resolve()}")
    print("=" * 60)
    logger.info("=== 出征准备页面交互式测试结束 ===")


if __name__ == "__main__":
    main()
